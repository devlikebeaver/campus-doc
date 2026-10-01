const fs=require('fs'),CFB=require('../vendor/cfb.cjs');
const [out,recipe]=process.argv.slice(2);if(!out||!recipe)throw new Error('output recipe required');
const streams=JSON.parse(fs.readFileSync(recipe,'utf8'));
const file=CFB.utils.cfb_new({root:'Root Entry'});
for(const [name,hex] of Object.entries(streams))CFB.utils.cfb_add(file,name,Buffer.from(hex,'hex'));
const bytes=CFB.write(file,{type:'buffer'}),back=CFB.read(bytes,{type:'buffer'});
for(const [name,hex] of Object.entries(streams)){
 const e=CFB.find(back,back.FullPaths[0]+name);if(!e||!Buffer.from(e.content).equals(Buffer.from(hex,'hex')))throw new Error('Stream mismatch '+name);
}
fs.writeFileSync(out,bytes);console.log(JSON.stringify({created_ole_streams:Object.keys(streams).length,verification:'passed'}));
