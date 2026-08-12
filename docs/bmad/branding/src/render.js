const {Resvg} = require('/tmp/svgrender/node_modules/@resvg/resvg-js');
const fs=require('fs'), path=require('path');
const OUT='out';
// name -> array of widths to export
const jobs = {
  'mark-8crest-on-dark':[512,256], 'mark-8crest-on-light':[512],
  'mark-8crest-reversed':[512], 'mark-8crest-mono-dark':[512], 'mark-8crest-mono-light':[512],
  'mark-formation-on-dark':[512], 'mark-formation-on-light':[512], 'mark-formation-mono-dark':[512],
  'mark-helm-recrewed-on-dark':[512],
  'favicon':[16,32,48,64], 'favicon-mono':[32],
  'banner-on-dark':[1180], 'banner-on-light':[1180], 'banner-mono-dark':[1180], 'banner-terminal-mono':[1180],
  'readme-banner':[1280],
};
for(const [name,widths] of Object.entries(jobs)){
  const svg=fs.readFileSync(path.join(OUT,name+'.svg'));
  for(const w of widths){
    const r=new Resvg(svg,{fitTo:{mode:'width',value:w}, font:{loadSystemFonts:false}});
    const png=r.render().asPng();
    const suffix = widths.length>1 ? `-${w}` : '';
    fs.writeFileSync(path.join(OUT,name+suffix+'.png'), png);
  }
}
console.log('rendered');
