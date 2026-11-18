"""Milestone 1 gateway HTTP commands and WebSocket status."""
import argparse
import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field,StrictInt
import uvicorn
from system import ProductionSystem

ROOT=Path(__file__).resolve().parents[1]

class ConnectRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    serial_port:str=Field(min_length=1,max_length=32)
    host:str=Field(min_length=1,max_length=253)
    port:StrictInt=Field(default=9000,ge=1,le=65535)

class CommandRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str
    values:dict[str,StrictInt]=Field(default_factory=dict)
    cmd_id:StrictInt=Field(ge=1,le=0xffffffff)

def create_app(system=None,folder=None):
    owns_system=system is None
    if system is None:system=ProductionSystem(folder or ROOT/'logs'/f'milestone1-{time.time_ns()}')
    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns_system:await asyncio.to_thread(system.close)
    app=FastAPI(title='MCT431 Milestone 1',lifespan=lifespan)
    app.state.system=system

    @app.get('/')
    def index():return FileResponse(ROOT/'Gateway/static/index.html')

    @app.get('/api/status')
    def status():return system.snapshot()

    @app.post('/api/command-id')
    def command_id():
        try:return {'cmd_id':system.reserve_identifier(),'expires_in_seconds':5}
        except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc

    @app.get('/api/setup')
    def setup():
        path=ROOT/'.tools/inspection-network.json'
        return {'serial_port':'COM7',**(json.loads(path.read_text()) if path.exists() else {})}

    @app.post('/api/connect')
    def connect(body:ConnectRequest):
        try:return system.connect(body.serial_port,body.host,body.port)
        except (ValueError,RuntimeError,TimeoutError,ConnectionError,OSError) as exc:
            raise HTTPException(status_code=409,detail=str(exc)) from exc

    @app.post('/api/command')
    def command(body:CommandRequest):
        try:return system.command(body.action,body.values,body.cmd_id)
        except (ValueError,RuntimeError,TimeoutError,ConnectionError,OSError) as exc:
            system.release_identifier(body.cmd_id)
            raise HTTPException(status_code=409,detail=str(exc)) from exc

    @app.websocket('/ws/status')
    async def websocket(ws:WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(system.snapshot())
                await asyncio.sleep(.2)
        except (WebSocketDisconnect,RuntimeError):pass
    return app

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind',default='127.0.0.1',help='Use 0.0.0.0 for a separate LAN operator PC')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--log-dir')
    args=parser.parse_args()
    uvicorn.run(create_app(folder=args.log_dir),host=args.bind,port=args.port)

if __name__=='__main__':main()
