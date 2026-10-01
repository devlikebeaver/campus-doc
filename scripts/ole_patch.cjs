/* Narrow OLE stream replacement; third-party CFB 1.2.2 is vendored with its license. */
const fs = require('fs');
const CFB = require('../vendor/cfb.cjs');
const [src,out,recipe] = process.argv.slice(2);
if (!src || !out || !recipe || src===out) throw new Error('source output recipe required');
const old = CFB.read(fs.readFileSync(src), {type:'buffer'});
const changes = JSON.parse(fs.readFileSync(recipe,'utf8'));
const root = old.FullPaths[0];
const originals = new Map();
for (let i=0; i<old.FullPaths.length; i++) {
  const entry = old.FileIndex[i];
  if(entry.type===2) originals.set(old.FullPaths[i],Buffer.from(entry.content));
}
for (const [name,hex] of Object.entries(changes)) {
  const full=root+name;
  if (!originals.has(full)) throw new Error('Unknown stream '+name);
  CFB.utils.cfb_add(old,full,Buffer.from(hex,'hex'));
}
const bytes=CFB.write(old,{type:'buffer'});
const reopened=CFB.read(bytes,{type:'buffer'});
for (const [name,b] of originals) {
  const entry=CFB.find(reopened,name);
  const desired=changes[name.slice(root.length)] ? Buffer.from(changes[name.slice(root.length)],'hex') : b;
  if(!entry || !Buffer.from(entry.content).equals(desired)) throw new Error('Stream mismatch '+name);
}
fs.writeFileSync(out,bytes);
console.log(JSON.stringify({ole_stream_verification:'passed',streams:originals.size}));
