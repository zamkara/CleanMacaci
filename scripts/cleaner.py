#!/usr/bin/python3
"""Dynamic cache discovery with conservative deletion boundaries."""
import argparse,datetime,fcntl,json,os,pathlib,shutil,subprocess,sys,tempfile,time
import importlib.util
_module_path=pathlib.Path(__file__).resolve().with_name("omarchy-cleaner-discovery.py")
if not _module_path.exists(): _module_path=pathlib.Path(__file__).resolve().with_name("discovery.py")
_spec=importlib.util.spec_from_file_location("cleaner_discovery",_module_path); discovery=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(discovery)
USER_HOME=pathlib.Path.home();CACHE=pathlib.Path(os.environ.get("XDG_CACHE_HOME",USER_HOME/".cache"));STATE=pathlib.Path(os.environ.get('XDG_STATE_HOME',USER_HOME/'.local/state'))/'CleanMacaci'

def run(args,timeout=15):
 return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
def processes():
 p=run(['ps','-u',str(os.getuid()),'-o','comm=']);return set(p.stdout.lower().splitlines())
def busy(names,procs):return any(any(n in comm for n in names) for comm in procs)
def size(path):
 total=0;seen=set();stack=[path]
 while stack:
  p=stack.pop()
  try:
   st=p.lstat();key=(st.st_dev,st.st_ino)
   if key in seen:continue
   seen.add(key)
   if not p.is_dir():total+=st.st_blocks*512
   if p.is_dir() and not p.is_symlink():
    with os.scandir(p) as entries:stack.extend(pathlib.Path(e.path) for e in entries)
  except (FileNotFoundError,PermissionError,OSError):pass
 return total

def valid(path):
 return any(discovery.within(path.absolute(),root.absolute()) for root in discovery.roots(USER_HOME)+discovery.project_roots(USER_HOME))

def legacy_categories():
 import hashlib,re
 procs=processes();installed=set(run(['pacman','-Qq']).stdout.splitlines())
 building=busy(['yay','paru','makepkg','cargo','rustc','pnpm','npm','bun'],procs)
 rows=[]
 def add(path,paths,label,reason,confidence='review',blocked=False,default=False):
  paths=[p for p in paths if p.exists() and valid(p)]
  amount=sum(size(p) for p in paths)
  if not amount:return
  rows.append(dict(id=hashlib.sha256(str(path).encode()).hexdigest()[:16],label=label,paths=paths,bytes=amount,blocked=blocked,reason=reason,confidence=confidence,default=default,selected=default and not blocked))
 if not CACHE.is_dir() or CACHE.is_symlink():return []
 # Inventory comes from actual disk contents. No fixed application/category list.
 for top in sorted(CACHE.iterdir()):
  if top.is_symlink():continue
  if not valid(top):continue
  children=list(top.iterdir()) if top.is_dir() else []
  names={top.name.lower(),*[c.name.lower() for c in children]}
  tokens={re.sub(r'[^a-z0-9]','',n) for n in names if len(n)>3}
  active=any(t in re.sub(r'[^a-z0-9]','',comm) for t in tokens for comm in procs)
  # Package metadata identifies build workspaces and whether the package was installed.
  workspaces=[c for c in children if c.is_dir() and not c.is_symlink() and (c/'PKGBUILD').is_file()]
  if workspaces:
   for workspace in workspaces:
    pkg_names=[]
    metadata=workspace/'.SRCINFO'
    if metadata.is_file():
     pkg_names=re.findall(r'^\s*pkgname\s*=\s*(\S+)',metadata.read_text(errors='replace'),re.M)
    exists=any(name in installed for name in pkg_names)
    paths=[c for c in workspace.iterdir() if c.name in ('src','pkg') or (c.is_file() and c.name.endswith(('.tar.gz','.tar.xz','.tar.bz2','.zip','.deb','.AppImage')))]
    if shutil.which('paccache'):
     try:
      old=run(['paccache','-d','-k','3','-c',str(workspace),'-v','-v','-z','--nocolor'])
      paths.extend(pathlib.Path(x.strip()) for x in old.stdout.split('\0') if x.strip().startswith(str(workspace)) and pathlib.Path(x.strip()).is_file())
     except (OSError,subprocess.TimeoutExpired):pass
    status='Installed package' if exists else 'Uninstalled / interrupted build'
    add(workspace,paths,workspace.name+' build cache',status+'; review extracted sources and local build edits before cleaning. Package recipes and rollback archives are retained.','review',building,False)
   continue
  if top.is_file():
   add(top,[top],top.name,'Cache file; review before deleting.','review',active,False);continue
  if any('shader' in n or 'pipeline' in n or n=='fontconfig' for n in names):
   add(top,[top],top.name,'Performance cache; removing it can cause recompilation and stutter.','preserve',True,False);continue
  # State-like files override cache-location hints. Do not assume every .cache entry is junk.
  stateful=any(c.name.lower().endswith(('.sqlite','.sqlite3','.db','.db-wal')) or c.name.lower() in ('sessions','cookies','history','profiles') for c in children)
  if stateful:
   add(top,[top],top.name,'Contains state-like data; retained for manual review.','preserve',True,False);continue
  generated=[c for c in children if c.is_dir() and c.name.lower().replace('-','_') in ('cache','cache2','code cache','code_cache','cacheddata','images','thumbnails')]
  if active:
   add(top,generated or [top],top.name,'Application is running; close it before cleaning.','safe' if generated else 'review',True,False);continue
  if generated:
   add(top,generated,top.name+' generated cache','Cache-like layout; review before deleting.','review',False,False)
  elif 'thumbnails' in names:
   add(top,[top],top.name,'Regenerable thumbnail cache.','safe',False,True)
  else:
   add(top,[top],top.name,'Unclassified cache directory; inspect before selecting.','review',False,False)
 return sorted(rows,key=lambda r:r['bytes'],reverse=True)

def categories():
 detailed,coverage=discovery.discover(USER_HOME,size,processes())
 developer,project_coverage=discovery.developer_discovery(USER_HOME,size)
 detailed+=developer;coverage+=project_coverage
 legacy=legacy_categories()
 # A broad ancestor row must never overlap finer cache / personal-data entries.
 rows=[r for r in legacy if not any(a==b or a.is_relative_to(b) or b.is_relative_to(a) for a in r['paths'] for d in detailed for b in d['paths'])]
 categories.coverage=coverage
 allrows=rows+detailed
 try:
  process_map={}
  for line in run(['ps','-u',str(os.getuid()),'-o','pid=,comm=']).stdout.splitlines():
   parts=line.strip().split(None,1)
   if len(parts)==2:process_map[int(parts[0])]=parts[1].lower()
  clients=json.loads(run(['hyprctl','clients','-j']).stdout)
  for row in allrows:
   names=row.get('active_names',[])
   if row['blocked'] and not names and row.get('confidence')!='preserve':
    for path in row['paths']:
     for base in discovery.roots(USER_HOME):
      if path.is_relative_to(base):names+=discovery.app_names(path,base,set(process_map.values()))
   row['windows']=[dict(address=w['address'],title=w.get('title',''),app=w.get('class','')) for w in clients if w.get('mapped') and process_map.get(w.get('pid')) in names]
 except (OSError,ValueError,subprocess.TimeoutExpired):
  for row in allrows:row['windows']=[]
 return sorted(allrows,key=lambda r:(not r['selected'],r['blocked'],-r['bytes']))

def close_apps(key):
 rows={r['id']:r for r in categories()}
 row=rows.get(key)
 if not row or not row.get('windows'):raise ValueError('No matching application windows remain. Scan again.')
 closed=[]
 for window in row['windows']:
  address=window['address']
  if not __import__('re').fullmatch(r'0x[0-9a-fA-F]+',address):continue
  result=run(['hyprctl','dispatch','hl.dsp.window.close({ window = '+json.dumps('address:'+address)+' })'])
  if result.returncode:raise ValueError(result.stderr or result.stdout)
  closed.append(window)
 return {'close_requested':closed,'note':'Normal close requested. Unsaved work may prompt; scan again after the app exits.'}

def system_sources():
 sources=[]
 def command(args):
  try:
   r=run(args,timeout=20)
   return r.stdout.strip(),r.stderr.strip(),r.returncode
  except (OSError,subprocess.TimeoutExpired) as e:return '',str(e),1
 out,err,code=command(['pacman-conf','CacheDir'])
 for raw in out.splitlines():
  path=pathlib.Path(raw)
  candidates,problem,status=command(['paccache','-d','-k','3','-c',str(path),'-v','-v','-z','--nocolor'])
  files=[pathlib.Path(x.strip()) for x in candidates.split('\0') if x.strip().startswith(str(path))]
  sources.append(dict(label='Pacman package cache',path=str(path),candidate_bytes=sum(size(f) for f in files),candidate_count=len(files),policy='Keep the newest 3 versions per package.',status='available' if status==0 else 'unavailable',detail=problem))
 journal,err,code=command(['journalctl','--disk-usage','--no-pager'])
 sources.append(dict(label='System journal',policy='Keep up to 14 days and 200 MiB of archived logs.',status='available' if code==0 else 'restricted',detail=journal or err))
 config,err,code=command(['systemd-tmpfiles','--cat-config'])
 for path in ('/tmp','/var/tmp'):
  rules=[line for line in config.splitlines() if line.strip() and not line.lstrip().startswith('#') and len(line.split())>=2 and line.split()[1]==path]
  sources.append(dict(label='Temporary files',path=path,policy='Follow configured age, access-time and exclusion rules.',rules=rules,status='available' if rules else 'no configured age rule'))
 return sources

def keep_paths():
 config=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',USER_HOME/'.config'))/'omarchy/cleanmacaci.json'
 if not config.exists():config=config.with_name('cleaner.json')
 if not config.exists():return []
 data=json.loads(config.read_text())
 values=data.get('keep',[])
 if not isinstance(values,list) or any(not isinstance(v,str) for v in values):raise ValueError('cleaner.json: keep must be a list of paths.')
 return [pathlib.Path(os.path.expandvars(v.replace('~',str(USER_HOME),1) if v.startswith('~') else v)).absolute() for v in values]

def apply_keep_rules(rows):
 kept=keep_paths()
 for row in rows:
  for path in row['paths']:
   if any(path==k or path.is_relative_to(k) or k.is_relative_to(path) for k in kept):
    row.update(blocked=True,selected=False,confidence='preserve',reason='Protected by your Cleaner keep list.');break
 return rows

def target_signature(paths):
 """Bind confirmation to the scanned tree; never cross a nested mount."""
 import hashlib,stat
 digest=hashlib.sha256();count=0
 for root in sorted(paths,key=str):
  device=root.lstat().st_dev;stack=[root]
  while stack:
   path=stack.pop();st=path.lstat();count+=1
   if count>1000000:raise ValueError('Cleanup target is too large to verify; narrow the selection.')
   if st.st_dev!=device or (path!=root and os.path.ismount(path)):raise ValueError('Nested filesystem is protected: '+str(path))
   record=(str(path),st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
   digest.update(repr(record).encode('utf-8','surrogateescape'))
   if stat.S_ISDIR(st.st_mode):stack.extend(sorted(path.iterdir(),key=str,reverse=True))
 return digest.hexdigest()

def bind_preview(rows):
 for row in rows:
  if row['blocked']:continue
  try:row['signature']=target_signature(row['paths'])
  except (OSError,ValueError) as error:
   row.update(blocked=True,selected=False,reason='Cannot safely verify this target: '+str(error))
 return rows

def public(rows):return [{**{k:v for k,v in r.items() if k!='paths'},'paths':[str(p) for p in r['paths']]} for r in rows]
def scan():
 rows=bind_preview(apply_keep_rules(categories()));info={'timestamp':datetime.datetime.now().isoformat(timespec='seconds'),'categories':public(rows),'coverage':categories.coverage,'system_sources':system_sources(),'safe_bytes':sum(r['bytes'] for r in rows if r['selected']),'note':'Categories are discovered from disk and package metadata. Private files, installed apps, containers, Trash and performance caches are not automatically cleaned.'}
 STATE.mkdir(parents=True,exist_ok=True)
 history=sorted(STATE.glob('cleanup-*.json'))
 if history:
  try:
   last=json.loads(history[-1].read_text());info['last_cleanup']={'timestamp':last['timestamp'],'removed_bytes':last.get('removed_bytes',last.get('reclaimed_bytes',0))}
  except (OSError,ValueError,KeyError):pass
 (STATE/'latest-scan.json').write_text(json.dumps(info,indent=2)+'\n');return info

def clean(ids):
 rows=apply_keep_rules(categories());eligible={r['id']:r for r in rows};unknown=set(ids)-eligible.keys()
 if unknown:raise ValueError('Scan changed; rescan before cleaning: '+','.join(unknown))
 try:preview=json.loads((STATE/'latest-scan.json').read_text())
 except (OSError,ValueError):raise ValueError('A successful preview scan is required before cleaning.')
 expected={r['id']:r for r in preview.get('categories',[])}
 # Validate the whole selection before deleting its first file.
 for key in ids:
  row=eligible[key];old=expected.get(key)
  if row['blocked']:continue
  if not old or old.get('blocked') or not old.get('signature'):raise ValueError('Selection was not eligible in the preview. Scan again.')
  if [str(p) for p in row['paths']]!=old['paths'] or target_signature(row['paths'])!=old['signature']:
   raise ValueError('Files changed since preview; nothing was deleted. Scan again: '+row['label'])
 free_before={}
 for key in ids:
  for path in eligible[key]['paths']:
   try:
    stats=os.statvfs(path);device=getattr(stats,'f_fsid',path.stat().st_dev)
    free_before.setdefault(device,(path.parent,stats.f_bavail*stats.f_frsize))
   except OSError:pass
 reclaimed=0;actions=[];errors=[]
 for key in ids:
  row=eligible[key]
  if row['blocked']:actions.append({'id':key,'status':'skipped','reason':row['reason']});continue
  for path in row['paths']:
   if not valid(path):errors.append({'path':str(path),'error':'Path redirected or outside approved discovery roots'});continue
   amount=size(path)
   print('Removing '+str(path),file=sys.stderr,flush=True)
   try:
    if path.is_dir() and row.get('kind') in ('cache','generated','site-cache','log','diagnostics'):
     # Preserve the application's cache directory permissions and identity.
     for child in path.iterdir():
      if child.is_dir() and not child.is_symlink():shutil.rmtree(child)
      else:child.unlink()
    elif path.is_dir():shutil.rmtree(path)
    else:path.unlink()
    reclaimed+=amount;actions.append({'id':key,'path':str(path),'bytes':amount,'status':'cleaned'})
   except (OSError,shutil.Error) as e:errors.append({'path':str(path),'error':str(e)})
 measured=0
 for parent,before in free_before.values():
  try:
   stats=os.statvfs(parent);measured+=max(0,stats.f_bavail*stats.f_frsize-before)
  except OSError:pass
 result={'timestamp':datetime.datetime.now().isoformat(timespec='seconds'),'removed_bytes':reclaimed,'reclaimed_bytes':measured,'actions':actions,'errors':errors}
 STATE.mkdir(parents=True,exist_ok=True);(STATE/('cleanup-'+str(time.time_ns())+'.json')).write_text(json.dumps(result,indent=2)+'\n');result['scan']=scan();return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--scan',action='store_true');parser.add_argument('--inventory',action='store_true');parser.add_argument('--clean');parser.add_argument('--clean-safe',action='store_true');parser.add_argument('--close-apps');args=parser.parse_args()
 STATE.mkdir(parents=True,exist_ok=True)
 with (STATE/'lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if args.close_apps:result=close_apps(args.close_apps)
  elif args.clean_safe:
   scan()
   result=clean([r['id'] for r in categories() if r['selected']])
  elif args.clean is not None:result=clean(list(dict.fromkeys(x for x in args.clean.split(',') if x)))
  else:result=scan()
  if args.inventory:
   inventory=[]
   for child in USER_HOME.iterdir():
    if child.is_dir() and not child.is_symlink():inventory.append({'path':str(child),'bytes':size(child)})
   result['inventory']=sorted(inventory,key=lambda r:r['bytes'],reverse=True)
   (STATE/'space-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'error':str(e)}));sys.exit(1)
