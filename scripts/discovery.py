"""Bounded, schema-aware discovery. Never walk through symbolic links."""
import hashlib,os,pathlib,re,sys,time
CACHE_NAMES={'cache','cache2','cache_data','code cache','gpucache','cacheddata','cached code','cachestorage','networkcache','media cache','_cacache','http-cache','webcache','thumbnails','images','artwork','http-v2','download-cache','caches'}
PERFORMANCE={'gpucache','shadercache','shader_cache','dawncache','grshadercache','fontconfig','mesa_shader_cache','nvidia','qmlcache','code cache','cacheddata'}
PRIVATE={'cookies':'Cookies & site data','cookies.sqlite':'Cookies & site data','history':'Browsing history','places.sqlite':'History & bookmarks','login data':'Saved passwords','logins.json':'Saved passwords','key4.db':'Encryption keys','web data':'Autofill data','permissions.sqlite':'Site permissions','local storage':'Site storage','indexeddb':'Site storage','storage':'Site storage','session storage':'Sessions','sessionstore.jsonlz4':'Sessions','favicons.sqlite':'Bookmarks icons','preferences':'Settings','local state':'Settings','sessions':'Sessions','sessionstore-backups':'Sessions'}
SKIP={'.git','node_modules','vendor','src','pkg','store','extensions','plugins','installs','Trash','containers','docker','libvirt'}
def roots(home):
 r=[pathlib.Path(os.environ.get('XDG_CACHE_HOME',home/'.cache')),pathlib.Path(os.environ.get('XDG_CONFIG_HOME',home/'.config')),pathlib.Path(os.environ.get('XDG_DATA_HOME',home/'.local/share')),pathlib.Path(os.environ.get('XDG_STATE_HOME',home/'.local/state')),home/'.mozilla',home/'.npm',home/'.cargo',home/'.java',home/'.icedtea',home/'.gradle']
 flat=home/'.var/app'
 if flat.is_dir() and not flat.is_symlink():
  for app in flat.iterdir():
   if app.is_dir() and not app.is_symlink():r.extend(app/sub for sub in ('cache','config','data'))
 return list(dict.fromkeys(r))
def within(path,root):
 if not path.is_relative_to(root) or path==root:return False
 current=path
 while current!=root.parent:
  if current.is_symlink():return False
  current=current.parent
 return not root.is_symlink()
def app_names(path,root,procs):
 parts=path.relative_to(root).parts[:3]
 aliases={'mozilla':['firefox','librewolf','floorp','zen'],'bravesoftware':['brave'],'google-chrome':['chrome'],'chromium':['chromium'],'code':['code'],'electron':['electron']}
 tokens=[]
 for p in parts:
  low=p.lower()
  if low=='mozilla' and any(x.lower()=='firefox' for x in parts):continue
  tokens.extend(aliases.get(low,[low]))
 normalized=[re.sub('[^a-z0-9]','',p) for p in procs]
 return [p for p,comm in zip(procs,normalized) if any((len(t)>=4 and re.sub('[^a-z0-9]','',t) in comm) or re.sub('[^a-z0-9]','',t)==comm for t in tokens)]
def app_active(path,root,procs):return bool(app_names(path,root,procs))
def profile_kind(parent):
 """Detect data formats rather than assuming that an application name is safe."""
 if (parent/'prefs.js').is_file() or (parent/'cookies.sqlite').is_file():return 'firefox'
 if (parent/'Preferences').is_file():return 'chromium'
 if (parent/'Local State').is_file() and any((parent/n).exists() for n in ('Cookies','Network','Local Storage')):return 'electron'
 return None

def classify_generated(path, profile):
 name=path.name.lower()
 if name in {'crashpad','crash reports','minidumps','pending pings'} and profile:
  return 'diagnostics',False,'Application crash / telemetry files. Review before removing diagnostic history.'
 if name in {'cache','cache2'}:
  verified=(name=='cache2' and (path/'entries').is_dir() and (path/'index').is_file()) or (name=='cache' and bool(profile) and (path/'Cache_Data').is_dir())
  if verified:return 'cache',True,'Verified browser HTTP cache. Cookies, sessions, passwords and settings are retained; pages will download resources again.'
 if name in {'cachestorage','service worker'} and profile:
  return 'site-cache',False,'Offline website / service-worker data. Cleaning can remove offline content; review before selecting.'
 return None

def discover(home,size,procs):
 rows=[];coverage=[];seen=set()
 for base in roots(home):
  if not base.is_dir() or base.is_symlink():continue
  print('Scanning '+str(base),file=sys.stderr,flush=True)
  count=0;errors=[];stack=[(base,0)];limited=False
  while stack:
   parent,depth=stack.pop()
   try: children=list(parent.iterdir())
   except OSError as e:errors.append(str(e));continue
   for p in children:
    count+=1
    if count>30000:limited=True;break
    if p.is_symlink():continue
    try:isdir=p.is_dir()
    except OSError:continue
    name=p.name.lower()
    # Installed runtimes/repositories are not cleanup candidates or scan trees.
    if parent.name=='flatpak' and name in ('app','runtime','repo'):continue
    if parent.name=='uv' and name=='python':continue
    if parent.name=='mise' and name in ('installs','shims'):continue
    profile=profile_kind(parent)
    if not profile and parent.name in ('Network','Service Worker'):profile=profile_kind(parent.parent)
    rule=classify_generated(p,profile)
    kind=None
    if profile and name in PRIVATE:kind='private'
    elif rule:kind=rule[0]
    elif base.name in ('cache','.cache') and not isdir and name.endswith(('.sqlite','.sqlite3','.db','.db-wal')):kind='private'
    elif p.parent.name=='omarchy' and name in ('image-selector','theme-selector'):kind='generated'
    elif p.parent.name=='omarchy' and re.fullmatch(r'keybindings-[a-f0-9]+\.records',name):kind='generated'
    elif name=='store' and parent.name=='pnpm':kind='store'
    elif name=='index' and parent.name=='registry' and base.name=='.cargo':kind='cache'
    elif name=='crashes' and p.parent.name=='quickshell':kind='diagnostics'
    elif name in CACHE_NAMES and isdir and (name not in ('images','artwork') or base.name in ('cache','.cache')):kind='performance' if name in PERFORMANCE else 'cache'
    elif name in PERFORMANCE and isdir:kind='performance'
    elif not isdir and (name.endswith(('.log','.log.old')) or re.search(r'\.log\.\d+(?:\.(?:gz|xz|zst))?$',name) or re.search(r'\.log\.(?:gz|xz|zst)$',name)):kind='log'
    if kind:
     if not within(p,base):continue
     amount=size(p)
     if amount and str(p) not in seen:
      seen.add(str(p));active=app_active(p,base,procs);blocked=active or kind in ('private','performance','store')
      rel=p.relative_to(base);app=' / '.join(rel.parts[:-1][-2:]) or base.name
      label=app+' · '+(PRIVATE.get(name,'Application database') if kind=='private' else ('Shared package store' if kind=='store' else ('Performance cache' if kind=='performance' else ('Logs' if kind in ('log','diagnostics') else p.name))))
      known_layout=(name=='cache2' and (p/'entries').is_dir() and (p/'index').exists()) or (name=='cache' and profile and (p/'Cache_Data').is_dir()) or (name=='thumbnails' and p.parent==base and base.name=='cache' or name=='thumbnails' and base.name=='.cache')
      automatic=kind=='generated' or (kind=='cache' and known_layout)
      if kind=='cache' and isdir:
       try:
        if any(child.name.lower() in PRIVATE or child.name.lower().endswith(('.sqlite','.db')) for child in p.iterdir()):automatic=False;rule=None
       except OSError:automatic=False;rule=None
      reason={'store':'Shared package store. Retained: use the package manager’s prune command to respect dependency references.','generated':'Generated Omarchy previews / keybinding index; recreated from the originals.','diagnostics':'Crash reports may be useful for debugging. Review before deleting.','private':'Personal application data; use the application’s own controls to clear selected data without damaging the profile.','performance':'Performance cache; retained to avoid recompilation and stutter.','site-cache':'Offline site cache; review before deleting.','cache':'Recognized generated-cache layout. Settings and profiles are retained.','log':'Application log file; review before removing diagnostic history.'}[kind]
      if rule:automatic=rule[1];reason=rule[2]
      if kind=='cache' and not automatic:reason='Cache-like directory without sufficient regeneration evidence; review before cleaning.'
      if active:reason='Application is running; close it and scan again. '+reason
      rows.append(dict(id=hashlib.sha256(str(p).encode()).hexdigest()[:16],label=label,paths=[p],bytes=amount,blocked=blocked,reason=reason,confidence='preserve' if kind in ('private','performance','store') else ('safe' if automatic else 'review'),default=automatic,selected=automatic and not blocked,active_names=app_names(p,base,procs),kind=kind,source=str(base)))
     if isdir:continue
    if isdir and depth<8 and p.name not in SKIP and not re.search(r'(^|[-_.])(backups?|snapshots?|bak)([-_.]|$)',name):stack.append((p,depth+1))
   if limited:break
  coverage.append({'path':str(base),'entries_checked':count,'limited':limited,'errors':errors[:8],'depth_limit':8})
 # Group log files and protected stores by profile; paths stay exact leaves.
 grouped={}
 for row in rows:
  key=(str(row['paths'][0].parent),row['kind'],row['label'] if row['kind']=='private' else '') if row['kind'] in ('log','private') else (row['id'],)
  if key in grouped:
   grouped[key]['paths']+=row['paths']; grouped[key]['bytes']+=row['bytes']
  else: grouped[key]=row
 return list(grouped.values()),coverage

MANIFESTS={'package.json','Cargo.toml','pyproject.toml','requirements.txt','go.mod','pom.xml','build.gradle','build.gradle.kts','composer.json'}
def project_roots(home):
 result=[home/'Projects',home/'Work',home/'Documents']
 try:
  result.extend(p for p in home.iterdir() if p.is_dir() and not p.is_symlink() and any((p/m).is_file() for m in MANIFESTS))
 except OSError:pass
 return list(dict.fromkeys(result))
def developer_discovery(home,size,entry_limit=20000):
 import subprocess
 from collections import deque
 rows=[];coverage=[];running=[]
 # Only a process whose working directory is inside a project blocks it.
 for proc in pathlib.Path('/proc').iterdir():
  if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
  try:
   if proc.stat().st_uid==os.getuid():
    name=(proc/'comm').read_text().strip().lower()
    if name in {'node','nodejs','npm','pnpm','yarn','bun','deno','cargo','rustc','python','python3','java','gradle','mvn','php','composer','go','nvim','vim','code','zed','eslint','tsserver','vite'}:running.append((proc/'cwd').resolve(strict=True))
  except OSError:pass
 for base in project_roots(home):
  if not base.is_dir() or base.is_symlink():continue
  print('Inspecting projects in '+str(base),file=sys.stderr,flush=True)
  stack=deque([(base,0)]);count=0;errors=[];limited=False
  while stack:
   project,depth=stack.popleft()
   try:
    with os.scandir(project) as listing:children=sorted((pathlib.Path(e.path) for e in listing if e.is_dir(follow_symlinks=False)),key=lambda p:(not any((p/m).is_file() for m in MANIFESTS),p.name))
   except OSError as e:errors.append(str(e));continue
   manifests={m for m in MANIFESTS if (project/m).is_file()}
   specs={}
   if 'package.json' in manifests:
    lock=any((project/n).is_file() for n in ('package-lock.json','pnpm-lock.yaml','yarn.lock','bun.lock','bun.lockb'))
    if lock:specs['node_modules']='Dependencies can be reinstalled from the lockfile. Local edits inside dependencies will be lost.'
    for n in ('.next','.nuxt','.svelte-kit','.angular','.parcel-cache','.turbo','coverage','dist','build','out'):specs[n]='Framework / build output. Review the path; rebuilding may need network access and time.'
   if 'Cargo.toml' in manifests:specs['target']='Rust build artifacts. Cargo will rebuild them; recompilation may take time.'
   if manifests & {'pyproject.toml','requirements.txt'}:
    for n in ('.venv','venv','.pytest_cache','.mypy_cache','.ruff_cache','__pycache__','htmlcov'):specs[n]='Python environment or generated tool output. Recreate dependencies / results after cleaning.'
   if manifests & {'pom.xml','build.gradle','build.gradle.kts'}:
    for n in ('target','build','.gradle'):specs[n]='Java build artifacts. Dependencies and build output may need downloading / compiling again.'
   if 'composer.json' in manifests and (project/'composer.lock').is_file():specs['vendor']='Composer dependencies. Reinstall from composer.lock; local dependency edits will be lost.'
   candidates=set()
   for name,reason in specs.items():
    p=project/name
    if not p.is_dir() or not within(p,base) or p.is_symlink():continue
    if name in ('.venv','venv') and not (p/'pyvenv.cfg').is_file():continue
    candidates.add(name)
    print('Measuring '+str(p),file=sys.stderr,flush=True)
    amount=size(p)
    if not amount:continue
    tracked=False;git_failed=False
    try:
     result=subprocess.run(['git','-C',str(project),'ls-files','--',name],capture_output=True,text=True,timeout=5)
     tracked=bool(result.stdout.strip()) if result.returncode==0 else False
     git_failed=result.returncode not in (0,128)
    except (OSError,subprocess.TimeoutExpired):git_failed=True
    active=any(cwd==project or cwd.is_relative_to(project) for cwd in running)
    blocked=tracked or git_failed or active
    if tracked:reason='Contains files tracked by Git. Source-controlled content is protected.'
    elif git_failed:reason='Could not check Git tracking. Retained until that check succeeds.'
    elif active:reason='A running process is working inside this project. Stop it and scan again. '+reason
    rows.append(dict(id=hashlib.sha256(str(p).encode()).hexdigest()[:16],label=str(project.relative_to(base) or project.name)+' · '+name,paths=[p],bytes=amount,blocked=blocked,reason=reason,confidence='preserve' if tracked or git_failed else 'review',default=False,selected=False,kind='development',source=str(base),windows=[]))
   for child in children:
    count+=1
    if count>entry_limit:limited=True;break
    name=child.name
    if depth<5 and child.is_dir() and not child.is_symlink() and name not in candidates and name not in SKIP and name not in {'dist','build','target','.venv','venv','.next','.nuxt','.svelte-kit','.angular','.parcel-cache','.turbo','coverage','out','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache'} and not re.search(r'(^|[-_.])(backups?|snapshots?|bak)([-_.]|$)',name):stack.append((child,depth+1))
   if limited:break
  coverage.append(dict(path=str(base),entries_checked=count,limited=limited,errors=errors[:8],depth_limit=5))
 return rows,coverage
