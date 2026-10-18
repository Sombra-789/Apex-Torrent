"""Fase 5: test unitario sin PySide6 ni antivirus externo instalado."""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations import (BRIDGE_PROTOCOL, IntegrationError, capability, executable_path,
                          integration_state, selected_complete_file, selected_folder,
                          start_companion)
from state import VERSION, Store


class CompanionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.exe = self.base / 'Thunderbolt.exe'
        self.exe.write_bytes(b'fake-not-executed')
        self.smart = self.base / 'SmartFiles.exe'
        self.smart.write_bytes(b'fake-not-executed')
        self.root = self.base / 'downloads'
        self.root.mkdir()
        self.finished = self.root / 'imagen.iso'
        self.finished.write_bytes(b'datos test')
        self.outside = self.base / 'elsewhere.exe'
        self.outside.write_bytes(b'outside')

    def manifest(self, app='thunderbolt', action='scan_file'):
        (self.base / 'apex-bridge.json').write_text(json.dumps({
            'protocol': BRIDGE_PROTOCOL, 'app': app,
            'actions': [action]}),encoding='utf-8')

    def test_version(self):
        self.assertEqual(VERSION, '1.3.8')

    def test_executable_validations(self):
        self.assertEqual(executable_path(str(self.exe)),self.exe.resolve())
        for bad in ('', str(self.root), str(self.root/'not_here.exe'),str(self.finished)):
            with self.subTest(bad=bad), self.assertRaises(IntegrationError):
                executable_path(bad)

    def test_no_capability_without_manifest(self):
        self.assertFalse(capability(self.exe,'thunderbolt','scan_file'))
        self.assertIn('apertura manual',integration_state(str(self.exe),'thunderbolt'))

    def test_manifest_exact_match(self):
        self.manifest()
        self.assertTrue(capability(self.exe,'thunderbolt','scan_file'))
        self.assertFalse(capability(self.exe,'smart_files','open_folder'))
        self.assertFalse(capability(self.exe,'thunderbolt','open_folder'))
        self.assertFalse(capability(self.exe,'other','scan_file'))
        self.assertIn('Conectado',integration_state(str(self.exe),'thunderbolt'))

    def test_reject_invalid_and_oversized_manifest(self):
        path=self.base/'apex-bridge.json'
        path.write_text('[]',encoding='utf8')
        self.assertFalse(capability(self.exe,'thunderbolt','scan_file'))
        path.write_bytes(b'x'*5000)
        self.assertFalse(capability(self.exe,'thunderbolt','scan_file'))
        path.write_text('{invalido')
        self.assertFalse(capability(self.exe,'thunderbolt','scan_file'))

    def test_manual_open_has_no_file_argument(self):
        with patch('integrations.subprocess.Popen') as pop:
            self.assertEqual(start_companion(str(self.exe),'thunderbolt'),'open')
        argv=pop.call_args.args[0]
        self.assertEqual(argv,[str(self.exe)])
        self.assertFalse(pop.call_args.kwargs['shell'])

    def test_scan_without_capability_does_not_start_program(self):
        with patch('integrations.subprocess.Popen') as pop:
            with self.assertRaises(IntegrationError):
                start_companion(str(self.exe),'thunderbolt','scan_file',self.finished)
        pop.assert_not_called()

    def test_scan_explicit_capability_has_no_shell(self):
        self.manifest()
        with patch('integrations.subprocess.Popen') as pop:
            self.assertEqual(start_companion(str(self.exe),'thunderbolt','scan_file',self.finished),'requested')
        self.assertEqual(pop.call_args.args[0],[str(self.exe),'--apex-scan-file',str(self.finished)])
        self.assertFalse(pop.call_args.kwargs['shell'])

    def test_open_folder_only_explicit_capability(self):
        self.manifest('smart_files','open_folder')
        with patch('integrations.subprocess.Popen') as pop:
            self.assertEqual(start_companion(str(self.smart),'smart_files','open_folder',self.root),'requested')
        self.assertEqual(pop.call_args.args[0],[str(self.smart),'--apex-open-folder',str(self.root)])

    def test_symlink_escape_and_incomplete(self):
        self.assertEqual(selected_complete_file(str(self.root),str(self.finished),True),self.finished)
        with self.assertRaises(IntegrationError):
            selected_complete_file(str(self.root),str(self.finished),False)
        with self.assertRaises(IntegrationError):
            selected_complete_file(str(self.root),str(self.outside),True)
        symlink=self.root/'escape.exe'
        try:
            symlink.symlink_to(self.outside)
        except (OSError,NotImplementedError):
            pass
        else:
            with self.assertRaises(IntegrationError):
                selected_complete_file(str(self.root),str(symlink),True)

    def test_directory_validated(self):
        self.assertEqual(selected_folder(str(self.root)),self.root)
        with self.assertRaises(IntegrationError):
            selected_folder(str(self.outside))

    def test_no_automatic_resumes_or_external_side_effects(self):
        store=Store(self.base/'config')
        store.save_json('integrations.json',{'thunderbolt':str(self.exe)})
        self.assertEqual(store.load_json('integrations.json',{})['thunderbolt'],str(self.exe))
        self.assertNotIn('integrations.json',str(self.root))

    def test_ui_contract_and_safe_banner(self):
        code=(Path(__file__).resolve().parents[1]/'app'/'ui.py').read_text(encoding='utf-8')
        ast.parse(code)
        self.assertIn('Ecosistema Apex',code)
        self.assertIn('selected_complete_file(root, file_name, True)',code)
        self.assertIn('sin resultado',code.lower() if 'sin resultado' in code.lower() else code.replace('No hay resultado', 'sin resultado'))
        self.assertIn('self.insight_text.setToolTip(result.report())',code)
        self.assertIn('setTabToolTip(6',code)


if __name__ == '__main__':
    unittest.main()
