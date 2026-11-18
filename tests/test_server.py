from fastapi.testclient import TestClient
from server import create_app
from test_system import Source,Inspector
from system import ProductionSystem

def test_http_validation_and_websocket_live_status(tmp_path):
    system=ProductionSystem(tmp_path,Source,Inspector)
    try:
        with TestClient(create_app(system)) as client:
            def command(action,values=None):
                identifier=client.post('/api/command-id').json()['cmd_id']
                return client.post('/api/command',json={'cmd_id':identifier,'action':action,'values':values or {}})
            assert client.get('/').status_code==200
            assert client.get('/api/status').json()['state']=='Idle'
            assert client.post('/api/connect',json={'serial_port':'COM7','host':'127.0.0.1'}).status_code==200
            malformed=client.post('/api/command',json={'action':'configure','values':{'target':'not a number'}})
            assert malformed.status_code==422
            assert command('start').status_code==409
            with client.websocket_connect('/ws/status') as ws:
                message=ws.receive_json()
                assert message['connected'] and message['state']=='Idle'
            response=command('configure',{'target':10,'cycle_ms':100,'inspection_ms':200,'n':5,'k':0,'capacity':4})
            assert response.status_code==200 and response.json()['phase']=='completion'
    finally:system.close()
