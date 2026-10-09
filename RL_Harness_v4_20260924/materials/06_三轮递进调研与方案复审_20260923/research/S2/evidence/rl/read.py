import pathlib,sys
root=pathlib.Path(__file__).parent
for spec in sys.argv[1:]:
 path,_,part=spec.partition(':');p=root/path
 if not p.exists(): print('MISSING',path);continue
 lines=p.read_text(encoding='utf-8-sig').splitlines();print('\nFILE',path)
 if part:
  for seg in part.split(','):
   a,_,b=seg.partition('-');a=int(a);b=int(b or a)
   for i in range(a-1,min(b,len(lines))):print(f'{i+1}: {lines[i]}')
 else:
  for i,l in enumerate(lines):print(f'{i+1}: {l}')
