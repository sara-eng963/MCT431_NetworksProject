"""Exercise the actual operator page against the real devices; save visual evidence."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--serial',required=True)
    parser.add_argument('--inspector',required=True)
    parser.add_argument('--output',default='logs/milestone1-20261118/dashboard')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    errors=[];requests=[];sockets=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
        page=browser.new_page(viewport={'width':1280,'height':900})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('websocket',lambda socket:sockets.append(socket.url))
        def request(req):
            if req.url.endswith('/api/command') and req.method=='POST':requests.append(json.loads(req.post_data))
        page.on('request',request)
        page.goto(args.base)
        expect(page.locator('#live')).to_have_text('Live status connected')
        page.locator('#serial').fill(args.serial);page.locator('#host').fill(args.inspector)
        page.locator('#connect').click()
        expect(page.locator('#message')).to_contain_text('Stations connected',timeout=15000)
        values={'target':3,'cycle_ms':800,'inspection_ms':200,'n':2,'k':1,'capacity':8}
        for key,value in values.items():page.locator('#'+key).fill(str(value))
        page.locator('#configure').click()
        expect(page.locator('#start')).to_be_enabled(timeout=15000)
        page.locator('#start').click()
        expect(page.locator('#outcome')).to_contain_text('Completed',timeout=20000)
        expect(page.locator('#produced')).to_have_text('3')
        expect(page.locator('#inspected')).to_have_text('3')
        expect(page.locator('#fault')).to_be_empty()
        assert requests and all(type(request['cmd_id']) is int for request in requests)
        assert sockets and not errors
        page.screenshot(path=str(folder/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.screenshot(path=str(folder/'mobile.png'),full_page=True)
        result={'passed':True,'javascript_errors':errors,'websocket_urls':sockets,
                'operator_commands':requests,'outcome':page.locator('#outcome').inner_text(),
                'produced':page.locator('#produced').inner_text(),'accepted':page.locator('#accepted').inner_text(),
                'rejected':page.locator('#rejected').inner_text(),'horizontal_overflow':False}
        (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2));browser.close()

if __name__=='__main__':main()
