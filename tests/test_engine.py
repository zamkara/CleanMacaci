import importlib.util,tempfile,pathlib,unittest,os
from unittest.mock import patch
s=importlib.util.spec_from_file_location('engine',pathlib.Path(__file__).resolve().parents[1]/'scripts/cleaner.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Safety(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=pathlib.Path(self.tmp.name)
  self.env=patch.dict(os.environ,{key:str(self.home/sub) for key,sub in [('XDG_CACHE_HOME','.cache'),('XDG_CONFIG_HOME','.config'),('XDG_DATA_HOME','.local/share'),('XDG_STATE_HOME','.local/state')]});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def put(self,path):
  p=self.home/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x'*8192);return p
 def rows(self,procs=set()):return m.discovery.discover(self.home,m.size,procs)[0]
 def test_browser_cache_and_private_data(self):
  self.put('.config/browser/Default/Preferences');cache=self.put('.config/browser/Default/Cache/Cache_Data/data');cookie=self.put('.config/browser/Default/Cookies')
  r=self.rows();self.assertTrue(any(cache.is_relative_to(x['paths'][0]) and not x['blocked'] for x in r));self.assertTrue(any(cookie in x['paths'] and x['blocked'] for x in r))
 def test_active_browser_blocked(self):
  self.put('.cache/mozilla/firefox/profile/cache2/entry');self.assertTrue(all(x['blocked'] for x in self.rows({'firefox'})))
 def test_symlink_not_followed(self):
  outside=self.home/'private';outside.mkdir();(outside/'secret').write_bytes(b'x'*8192)
  base=self.home/'.config/app';base.mkdir(parents=True);(base/'Cache').symlink_to(outside,target_is_directory=True);self.assertEqual(self.rows(),[])
 def test_backups_and_projects_excluded(self):
  self.put('.local/share/firefox-migration-backups/date/Cache/data');self.put('Projects/app/Cache/data');self.assertEqual(self.rows(),[])
 def test_no_overlapping_paths(self):
  self.put('.config/chromium/Default/Cache/Cache_Data/data');paths=[p for r in self.rows() for p in r['paths']]
  self.assertEqual(len(paths),1)
 def test_verified_firefox_cache_auto_selected(self):
  self.put('.cache/mozilla/firefox/profile/cache2/index');self.put('.cache/mozilla/firefox/profile/cache2/entries/item')
  row=self.rows()[0];self.assertTrue(row['default']);self.assertTrue(row['selected'])
  row=self.rows({'firefox'})[0];self.assertTrue(row['default']);self.assertFalse(row['selected']);self.assertTrue(row['blocked'])
 def test_unknown_cache_not_auto_selected(self):
  self.put('.config/example/Cache/custom-data');row=self.rows()[0]
  self.assertFalse(row['default']);self.assertEqual(row['confidence'],'review')
 def test_omarchy_generated_and_runtime_protection(self):
  self.put('.cache/omarchy/image-selector/thumb.jpg');self.put('.local/share/flatpak/runtime/example/Cache/content');self.put('.local/share/uv/python/example/Cache/content')
  rows=self.rows();self.assertEqual(len(rows),1);self.assertTrue(rows[0]['selected'])
 def test_close_only_uses_normal_window_close(self):
  old=m.categories,m.run
  calls=[]
  try:
   m.categories=lambda:[{'id':'a','windows':[{'address':'0xabc','title':'Example','app':'Example'}]}]
   def fake_run(args):
    calls.append(args)
    return type('Result',(),{'returncode':0,'stdout':'ok','stderr':''})()
   m.run=fake_run
   result=m.close_apps('a');self.assertEqual(len(result['close_requested']),1)
   self.assertIn('hl.dsp.window.close',calls[0][-1]);self.assertNotIn('kill',str(calls))
  finally:m.categories,m.run=old
 def test_short_process_names_are_detected(self):
  self.put('.cache/zen/profile/cache2/index');self.put('.cache/zen/profile/cache2/entries/item')
  self.assertTrue(self.rows({'zen'})[0]['blocked'])
 def test_project_dependencies_need_manifest_and_lock(self):
  self.put('Projects/app/package.json');self.put('Projects/app/package-lock.json');self.put('Projects/app/node_modules/pkg/file.js')
  self.put('Projects/unknown/node_modules/personal/file')
  rows,_=m.discovery.developer_discovery(self.home,m.size)
  self.assertEqual(len(rows),1);self.assertFalse(rows[0]['selected']);self.assertEqual(rows[0]['confidence'],'review')
 def test_tracked_build_output_protected(self):
  import subprocess
  manifest=self.put('Projects/app/package.json');artifact=self.put('Projects/app/dist/important.js');project=manifest.parent
  subprocess.run(['git','init','-q',str(project)],check=True)
  subprocess.run(['git','-C',str(project),'add','dist/important.js'],check=True)
  rows,_=m.discovery.developer_discovery(self.home,m.size)
  self.assertEqual(len(rows),1);self.assertTrue(rows[0]['blocked']);self.assertEqual(rows[0]['confidence'],'preserve')
 def test_dependency_symlink_never_followed(self):
  self.put('Projects/app/package.json');self.put('Projects/app/package-lock.json');target=self.home/'personal';target.mkdir();(target/'keep').write_text('keep')
  (self.home/'Projects/app/node_modules').symlink_to(target,target_is_directory=True)
  rows,_=m.discovery.developer_discovery(self.home,m.size);self.assertEqual(rows,[])
 def test_clean_preserves_profile_and_skips_private(self):
  pref=self.put('.config/browser/Default/Preferences');cookie=self.put('.config/browser/Default/Cookies');cache=self.put('.config/browser/Default/Cache/data')
  old=(m.USER_HOME,m.CACHE,m.STATE,m.categories,m.scan)
  try:
   m.USER_HOME=self.home;m.CACHE=self.home/'.cache';m.CACHE.mkdir();m.STATE=self.home/'reports';rows=self.rows();m.categories=lambda:rows;m.scan=lambda:{}
   m.STATE.mkdir();(m.STATE/'latest-scan.json').write_text(__import__('json').dumps({'categories':m.public(m.bind_preview(rows))}))
   self.assertTrue(all(p.is_relative_to(self.home) for r in rows for p in r['paths']));m.clean([r['id'] for r in rows]);self.assertTrue(pref.exists());self.assertTrue(cookie.exists());self.assertFalse(cache.exists())
  finally:m.USER_HOME,m.CACHE,m.STATE,m.categories,m.scan=old
 def test_nested_chromium_cookies_protected(self):
  self.put('.config/chromium/Default/Preferences');cookie=self.put('.config/chromium/Default/Network/Cookies')
  row=next(r for r in self.rows() if cookie in r['paths']);self.assertTrue(row['blocked'])
 def test_cache_with_private_database_never_auto_selected(self):
  self.put('.config/browser/Default/Preferences');self.put('.config/browser/Default/Cache/Cache_Data/data');self.put('.config/browser/Default/Cache/secret.db')
  row=next(r for r in self.rows() if r['paths']==[self.home/'.config/browser/Default/Cache']);self.assertFalse(row['selected'])
 def test_offline_site_cache_needs_review(self):
  self.put('.config/chromium/Default/Preferences');self.put('.config/chromium/Default/Service Worker/CacheStorage/data')
  row=next(r for r in self.rows() if r['paths']==[self.home/'.config/chromium/Default/Service Worker']);self.assertFalse(row['selected']);self.assertEqual(row['kind'],'site-cache')
 def test_browser_diagnostics_are_actionable_not_auto(self):
  self.put('.config/browser/Default/Preferences');self.put('.config/browser/Default/Crashpad/report.dmp')
  row=next(r for r in self.rows() if r['paths']==[self.home/'.config/browser/Default/Crashpad']);self.assertFalse(row['selected']);self.assertFalse(row['blocked']);self.assertEqual(row['kind'],'diagnostics')
 def test_rotated_compressed_logs_are_review_only(self):
  self.put('.local/state/app/output.log.2.gz');row=self.rows()[0]
  self.assertEqual(row['kind'],'log');self.assertFalse(row['selected'])
 def test_profile_settings_and_sessions_protected(self):
  pref=self.put('.config/browser/Default/Preferences');session=self.put('.config/browser/Default/Session Storage/session')
  rows=self.rows();self.assertTrue(any(pref in r['paths'] and r['blocked'] for r in rows));self.assertTrue(any(session.is_relative_to(p) and r['blocked'] for r in rows for p in r['paths']))
 def test_preview_change_prevents_all_deletion(self):
  import json
  first=self.put('.cache/one/Cache/a');second=self.put('.cache/two/Cache/a');rows=self.rows()
  old=(m.USER_HOME,m.STATE,m.categories)
  try:
   m.USER_HOME=self.home;m.STATE=self.home/'reports';m.STATE.mkdir();m.categories=lambda:rows
   (m.STATE/'latest-scan.json').write_text(json.dumps({'categories':m.public(m.bind_preview(rows))}))
   self.put('.cache/two/Cache/new-file')
   with self.assertRaisesRegex(ValueError,'Files changed'):m.clean([r['id'] for r in rows])
   self.assertTrue(first.exists());self.assertTrue(second.exists())
  finally:m.USER_HOME,m.STATE,m.categories=old
 def test_cleanup_preserves_cache_root_permissions(self):
  import json
  item=self.put('.config/app/Default/Preferences');data=self.put('.config/app/Default/Cache/Cache_Data/data');root=data.parent.parent;root.chmod(0o700);inode=root.stat().st_ino;rows=self.rows()
  old=(m.USER_HOME,m.STATE,m.categories,m.scan)
  try:
   m.USER_HOME=self.home;m.STATE=self.home/'reports';m.STATE.mkdir();m.categories=lambda:rows;m.scan=lambda:{}
   (m.STATE/'latest-scan.json').write_text(json.dumps({'categories':m.public(m.bind_preview(rows))}))
   m.clean([r['id'] for r in rows if not r['blocked']]);self.assertTrue(root.is_dir());self.assertEqual(root.stat().st_ino,inode);self.assertEqual(root.stat().st_mode&0o777,0o700);self.assertTrue(item.exists());self.assertFalse(data.exists())
  finally:m.USER_HOME,m.STATE,m.categories,m.scan=old
 def test_empty_directories_have_no_cleanable_bytes(self):
  p=self.home/'.cache/app/Cache';p.mkdir(parents=True);self.assertEqual(m.size(p),0);self.assertEqual(self.rows(),[])
 def test_keep_list_protects_parent_cleanup(self):
  import json
  item=self.put('.cache/app/Cache/important');rows=self.rows();config=self.home/'.config/omarchy/cleaner.json';config.parent.mkdir(parents=True);config.write_text(json.dumps({'keep':[str(item)]}))
  m.apply_keep_rules(rows);self.assertTrue(rows[0]['blocked']);self.assertFalse(rows[0]['selected'])
 def test_invalid_keep_list_fails_closed(self):
  config=self.home/'.config/omarchy/cleaner.json';config.parent.mkdir(parents=True);config.write_text('{"keep": true}')
  with self.assertRaises(ValueError):m.keep_paths()
 def test_legacy_java_and_gradle_caches_are_manual(self):
  self.put('.java/deployment/cache/data');self.put('.gradle/caches/output');self.put('.icedtea/cache/data')
  rows=self.rows();self.assertEqual(len(rows),3);self.assertTrue(all(not r['selected'] for r in rows))
 def test_backup_suffix_is_not_scanned(self):
  self.put('.config/app.bak/Cache/data');self.assertEqual(self.rows(),[])
 def test_aur_extracted_sources_are_not_automatically_selected(self):
  self.put('.cache/yay/example/PKGBUILD');self.put('.cache/yay/example/.SRCINFO');source=self.put('.cache/yay/example/src/edited.c')
  old=(m.USER_HOME,m.CACHE,m.run,m.processes)
  try:
   m.USER_HOME=self.home;m.CACHE=self.home/'.cache';m.processes=lambda:set();m.run=lambda args,**kwargs:type('Result',(),{'stdout':'','returncode':0})()
   rows=m.legacy_categories();self.assertEqual(len(rows),1);self.assertFalse(rows[0]['selected']);self.assertTrue(source.exists())
  finally:m.USER_HOME,m.CACHE,m.run,m.processes=old
 def test_manifest_project_scanned_before_large_unrelated_tree(self):
  for i in range(50):self.put('Projects/aaa-unrelated/tree/sub'+str(i)+'/file')
  self.put('Projects/rpd-example/package.json');self.put('Projects/rpd-example/pnpm-lock.yaml');self.put('Projects/rpd-example/node_modules/pkg/data')
  rows,coverage=m.discovery.developer_discovery(self.home,m.size,entry_limit=20)
  self.assertTrue(any(r['paths']==[self.home/'Projects/rpd-example/node_modules'] for r in rows));self.assertTrue(coverage[0]['limited'])
 def test_multiple_close_requests_deduplicate_windows(self):
  old=(m.categories,m.run);calls=[]
  try:
   window={'address':'0xabc','title':'Example','app':'Example'}
   m.categories=lambda:[{'id':key,'windows':[window]} for key in ('a','b')]
   m.run=lambda args:calls.append(args) or type('Result',(),{'returncode':0,'stdout':'','stderr':''})()
   self.assertEqual(len(m.close_apps('a,b')['close_requested']),1);self.assertEqual(len(calls),1)
   calls.clear()
   with self.assertRaises(ValueError):m.close_apps('a,missing')
   self.assertEqual(calls,[])
  finally:m.categories,m.run=old
if __name__=='__main__':unittest.main()
