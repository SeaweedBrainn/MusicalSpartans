// Optional real-browser regression. Run after npm test; see README.md.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),esbuild=require('esbuild');
const {chromium}=require('playwright');
(async()=>{
 const work=path.join(__dirname,'.tmp');fs.mkdirSync(work,{recursive:true});
 // Deliberately reproduce a typical Vite starter's centered flex root.
 fs.writeFileSync(path.join(work,'layout.html'),'<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;display:flex;place-items:center;min-width:320px;min-height:100vh}#root{max-width:1280px;margin:0 auto;padding:2rem;text-align:center}</style></head><body><div id="root"></div><script src="layout.js"></script></body></html>');
 fs.writeFileSync(path.join(work,'layout-entry.tsx'),`import React from 'react';import {createRoot} from 'react-dom/client';import {App} from './src/ui/App';import base from '../fixtures/v2.json';
 const game=structuredClone(base);game.run.summary.game_time_ms=180000;game.run.summary.score=1000000;game.run.notes=Array.from({length:2026},(_,i)=>({...base.run.notes[0],note_index:i,time_ms:i*88,latency_ms:i%121-60}));
 const callbacks=new Map();const state={message:'Game CSV files loaded',busy:false,jobId:'layout',revision:1,result:{job_id:'layout',status:'run_analyzed',game_run:game,crops:{}},server:'http://192.168.1.42:8000',captureSize:'medium',transferMethod:'auto',history:{currentSession:[],reports:[]},historyReady:true,chat:[],lastCoaching:null};
 globalThis.mentra={on:(n,cb)=>{callbacks.set(n,cb);return()=>{}},send:n=>{if(n==='get_state')callbacks.get('status')?.(state)},request:async()=>({dataUrl:''})};createRoot(document.getElementById('root')).render(<App/>);`);
 esbuild.buildSync({entryPoints:[path.join(work,'layout-entry.tsx')],bundle:true,platform:'browser',format:'iife',jsx:'automatic',nodePaths:[path.join(__dirname,'node_modules')],outfile:path.join(work,'layout.js')});
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
 try{
  for(const width of [320,393,430,768]){
   const page=await browser.newPage({viewport:{width,height:852}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(require('url').pathToFileURL(path.join(work,'layout.html')).href);
   await page.getByRole('navigation',{name:'Main pages'}).getByRole('button',{name:'Song',exact:true}).click();
   await page.getByRole('heading',{name:'Latency heatmap'}).waitFor();
   const layout=await page.evaluate(()=>{const chart=document.querySelector('.heatmap-scroll'),metrics=document.querySelector('.metrics');return {viewport:innerWidth,page:document.documentElement.scrollWidth,left:document.querySelector('.rhythm main').getBoundingClientRect().left,right:document.querySelector('.rhythm main').getBoundingClientRect().right,chartWidth:chart.clientWidth,chartScroll:chart.scrollWidth,columns:getComputedStyle(metrics).gridTemplateColumns.split(' ').length};});
   assert(layout.page<=width+1,`Page overflow at ${width}: ${JSON.stringify(layout)}`);assert(layout.left>=0&&layout.right<=width+1);assert(layout.chartScroll>layout.chartWidth,'Long heatmap must scroll within its own container');
   if(width<=430)assert.equal(layout.columns,1,'Mobile score cards should stack');
   await page.getByRole('region',{name:'Scrollable latency heatmap'}).evaluate(el=>{el.scrollLeft=500;});
   assert.equal(await page.evaluate(()=>scrollX),0,'Scrolling chart must not pan the whole page');
   await page.screenshot({path:path.join(work,`song-${width}.png`),fullPage:false});assert.deepEqual(errors,[]);await page.close();
  }
  console.log('PASS: 320/393/430/768px layouts, centered-flex starter reset, stacked mobile metrics, chart-only scrolling and no browser errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
