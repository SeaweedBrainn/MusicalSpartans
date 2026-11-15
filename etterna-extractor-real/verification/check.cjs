const fs=require('fs');
const path=require('path');
const {spawnSync}=require('child_process');
const work=path.join(__dirname,'.tmp');
fs.mkdirSync(work,{recursive:true});
fs.cpSync(path.join(__dirname,'../miniapp/src'),path.join(work,'src'),{recursive:true});
function run(args){
  const result=spawnSync(process.execPath,args,{cwd:work,stdio:'inherit'});
  if(result.status!==0)process.exit(result.status||1);
}
run([path.join(__dirname,'node_modules/typescript/bin/tsc'),'--noEmit','--strict','--noUnusedLocals',
  '--jsx','react-jsx','--target','ES2020','--module','ESNext','--moduleResolution','bundler',
  '--lib','ES2020,DOM','--skipLibCheck','src/background/index.ts','src/shared/channels.ts','src/ui/App.tsx']);
run([path.join(__dirname,'test-timing.cjs')]);
run([path.join(__dirname,'test-ui.cjs')]);
run([path.join(__dirname,'test-background.cjs')]);
