// Run after examples/local_agent_demo.py record + verify.
const {chromium}=require('playwright');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.REWIND_CHROMIUM?{executablePath:process.env.REWIND_CHROMIUM,args:['--no-sandbox']}:{})});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],network=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url())});
 await page.goto(pathToFileURL(path.resolve(process.argv[2]||'.rewind/local-agent-qualified/demo.html')).href);
 assert.equal(await page.locator('#runCount').innerText(),'4');
 assert.match(await page.locator('#mode').innerText(),/RECORDED MODEL · SIMULATED TOOLS/);
 await page.locator('#run').selectOption({index:3});
 await page.locator('#scrubber').fill('4');
 assert.match(await page.locator('#mode').innerText(),/WHAT-IF · mock continuation/);
 assert.match(await page.locator('#output').innerText(),/confirmed/);
 await page.getByText('Evidence chain & provenance',{exact:true}).click();
 assert.match(await page.locator('#lineage').innerText(),/Forked at #2/);
 assert.equal(await page.locator('#replays').innerText(),'50');
 await page.screenshot({path:'.rewind/local-agent-qualified/desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'.rewind/local-agent-qualified/mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
 await browser.close();console.log('PASS: actual-model provenance, explicit decision intervention, recovery, mobile and offline browser');
})().catch(e=>{console.error(e);process.exit(1)});
