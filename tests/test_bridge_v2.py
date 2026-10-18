"""Apex Bridge v2: tests sin red, sin PySide6 y sin ejecutar malware."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from bridge_ipc import (PROTOCOL, IntegrationError, prepare_ticket, read_request,
                        write_receipt, read_receipt, receiver_script, discard,
                        receipt_message, send_request)
from bridge_sdk import thunderbolt_handle, smart_files_handle
from bridge_relay import run as relay_run


class BridgeV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.data = self.base / 'local'
        self.downloads = self.base / 'downloads'
        self.downloads.mkdir()
        self.file = self.downloads / 'prueba.iso'
        self.file.write_bytes(b'contenido inofensivo')
        self.launcher = self.base / 'ABRIR_THUNDERBOLT.bat'
        self.launcher.write_text('@echo off\necho test')
        self.receiver = self.base / 'receiver.py'
        self.receiver.write_text('# muestra')

    def ticket(self, app='thunderbolt', action='scan_file'):
        target = self.file if action == 'scan_file' else self.downloads
        return prepare_ticket(self.data, app, action, target)

    def test_new_ticket_and_request_bound_to_random_id(self):
        t=self.ticket()
        obj=read_request(t.request_path,'thunderbolt')
        self.assertEqual(obj['request_id'],t.id)
        self.assertEqual(obj['target'],str(self.file.resolve()))
        self.assertEqual(obj['protocol'],PROTOCOL)
        self.assertFalse(t.receipt_path.exists())

    def test_refuse_nonexistent_and_wrong_type(self):
        with self.assertRaises(IntegrationError):
            prepare_ticket(self.data,'thunderbolt','scan_file',self.downloads)
        with self.assertRaises(IntegrationError):
            prepare_ticket(self.data,'smart_files','open_folder',self.file)
        with self.assertRaises(IntegrationError):
            prepare_ticket(self.data,'bad','open_folder',self.downloads)

    def test_receipt_requires_matching_identity_and_status(self):
        t=self.ticket()
        write_receipt(t.request_path,status='manual_required',message='Abra su antivirus')
        self.assertEqual(read_receipt(t)['status'],'manual_required')
        p=json.loads(t.receipt_path.read_text());p['request_id']='forged';t.receipt_path.write_text(json.dumps(p))
        with self.assertRaises(IntegrationError):read_receipt(t)

    def test_receipt_rejects_invented_verdict(self):
        t=self.ticket()
        with self.assertRaises(IntegrationError):
            write_receipt(t.request_path,status='manual_required',message='No hice análisis',verdict='clean')
        with self.assertRaises(IntegrationError):
            write_receipt(t.request_path,status='scan_finished',message='Listo',verdict='totally_safe')
        with self.assertRaises(IntegrationError):
            write_receipt(t.request_path,status='all_clear',message='Listo')

    def test_thunderbolt_without_engine_refuses_scan(self):
        t=self.ticket()
        self.assertEqual(thunderbolt_handle(t.request_path),'unsupported')
        self.assertEqual(read_receipt(t)['status'],'unsupported')

    def test_thunderbolt_real_callback_result(self):
        t=self.ticket()
        calls=[]
        def scan(path):
            calls.append(path);return 'inconclusive'
        self.assertEqual(thunderbolt_handle(t.request_path,scan),'scan_finished')
        self.assertEqual(calls,[self.file])
        self.assertEqual(read_receipt(t)['verdict'],'inconclusive')

    def test_thunderbolt_callback_failure_reports_failure(self):
        t=self.ticket()
        self.assertEqual(thunderbolt_handle(t.request_path,lambda _: (_ for _ in ()).throw(RuntimeError('scan failure'))),'scan_failed')
        self.assertEqual(read_receipt(t)['status'],'scan_failed')

    def test_smart_files_requires_actual_callback(self):
        t=self.ticket('smart_files','open_folder')
        self.assertEqual(smart_files_handle(t.request_path),'unsupported')
        self.assertEqual(read_receipt(t)['status'],'unsupported')

    def test_smart_files_actual_navigation(self):
        t=self.ticket('smart_files','open_folder')
        self.assertEqual(smart_files_handle(t.request_path,lambda path: path==self.downloads),'folder_opened')
        self.assertEqual(read_receipt(t)['status'],'folder_opened')

    def test_manifest_v2_requires_explicit_receiver(self):
        self.assertIsNone(receiver_script(self.launcher,'thunderbolt','scan_file'))
        manifest={'protocol':PROTOCOL,'app':'thunderbolt','actions':['scan_file'],'receiver':'receiver.py'}
        (self.base/'apex-bridge-v2.json').write_text(json.dumps(manifest))
        self.assertEqual(receiver_script(self.launcher,'thunderbolt','scan_file'),self.receiver)
        self.assertIsNone(receiver_script(self.launcher,'smart_files','open_folder'))
        manifest['receiver']='../outside.py'
        (self.base/'apex-bridge-v2.json').write_text(json.dumps(manifest))
        self.assertIsNone(receiver_script(self.launcher,'thunderbolt','scan_file'))

    def test_relay_acknowledges_manual_not_scan(self):
        t=self.ticket()
        with patch('bridge_relay.subprocess.Popen') as proc, patch('bridge_relay.os.startfile', create=True) as start:
            status=relay_run(t.request_path,self.launcher)
        self.assertEqual(status,'manual_required')
        self.assertEqual(read_receipt(t)['status'],'manual_required')
        self.assertNotIn('verdict',read_receipt(t))
        self.assertTrue(start.called if __import__('sys').platform == 'win32' else proc.called)

    def test_relay_smart_opens_external_folder(self):
        t=self.ticket('smart_files','open_folder')
        with patch('bridge_relay.subprocess.Popen'), patch('bridge_relay.os.startfile', create=True):
            self.assertEqual(relay_run(t.request_path,self.launcher),'folder_opened')
        self.assertEqual(read_receipt(t)['status'],'folder_opened')
        self.assertNotIn('verdict',read_receipt(t))

    def test_request_writer_launches_relay_without_shell(self):
        with patch('bridge_ipc.subprocess.Popen') as proc:
            ticket, mode=send_request(self.data,str(self.launcher),'thunderbolt','scan_file',self.file)
        self.assertEqual(mode,'manual_relay')
        self.assertFalse(proc.call_args.kwargs['shell'])
        self.assertTrue(ticket.request_path.exists())
        discard(ticket)
        self.assertFalse(ticket.request_path.exists())

    def test_messages_do_not_declare_manual_result_clean(self):
        t=self.ticket()
        write_receipt(t.request_path,status='manual_required',message='Abierto')
        msg=receipt_message(read_receipt(t),'thunderbolt','manual_relay')
        self.assertIn('MANUAL',msg)
        self.assertNotIn('seguro',msg)

    def test_expired_request_is_rejected(self):
        t=self.ticket()
        data=json.loads(t.request_path.read_text()); data['created_at']=1
        t.request_path.write_text(json.dumps(data))
        with self.assertRaises(IntegrationError):read_request(t.request_path)

    def test_file_symlink_escape_is_resolved(self):
        outside=self.base/'outside.iso'; outside.write_bytes(b'x')
        link=self.downloads/'link.iso'
        try:link.symlink_to(outside)
        except (OSError,NotImplementedError):self.skipTest('No symlink permission')
        t=prepare_ticket(self.data,'thunderbolt','scan_file',link)
        self.assertEqual(read_request(t.request_path)['target'],str(outside))
        # Caller must invoke selected_complete_file(root,link,True) before prepare_ticket.


if __name__=='__main__':unittest.main()
