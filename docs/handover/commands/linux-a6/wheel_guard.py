"""Guard pure wheel checks; genuine definitions are allowed, side effects are not."""
from contextlib import ExitStack,contextmanager
import http.client
import importlib.abc
from pathlib import Path
import socket,sqlite3,subprocess,sys
from unittest.mock import patch
from urllib.request import OpenerDirector

@contextmanager
def guarded_wheel(work,site):
    attempts=[]
    def forbidden(*a,**kw):
        attempts.append('forbidden operation')
        raise AssertionError('Pure wheel check forbids database/settings/network/process/API/worker/inference operations')
    def audit(event,args):
        if event.startswith('sqlite3.connect') or event in ('socket.connect','socket.bind','socket.getaddrinfo','socket.sendto','subprocess.Popen','os.system','os.posix_spawn'):
            forbidden()
        if event=='open' and isinstance(args[0],(str,bytes)):
            name=str(args[0]).lower()
            if name.endswith(('.sqlite','.sqlite3','.sqlite3-wal','.sqlite3-shm','.db','.db-wal','.db-shm','.dpapi','.pem','.key','.env')) or Path(name).name in ('local-ai.json','local-session.json','endpoint.json','workstation.json','private-model-key.txt'):
                forbidden()
    sys.addaudithook(audit)
    class NoServerImports(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0] in ('fastapi','uvicorn','openpyxl','tzdata') or fullname in ('dragonhydra.api','dragonhydra.jobs','dragonhydra.local_ai_service'):
                forbidden()
            return None
    finder=NoServerImports();sys.meta_path.insert(0,finder)
    assert sys.flags.isolated and sys.dont_write_bytecode and not sys.flags.optimize
    assert sys.version_info[:2]==(3,14) and site.is_dir()
    sys.path.insert(0,str(site))
    with ExitStack() as guards:
        for obj,name in ((sqlite3,'connect'),(socket.socket,'connect'),(socket.socket,'connect_ex'),(socket,'create_connection'),(OpenerDirector,'open'),(http.client.HTTPConnection,'connect'),(subprocess,'Popen')):
            guards.enter_context(patch.object(obj,name,forbidden))
        import dragonhydra
        from dragonhydra import local_ai,source_context
        from dragonhydra.cognition import memory
        from dragonhydra.product import Product
        from dragonhydra.connectors.core import Transport
        from dragonhydra.connectors.store import Store
        assert Path(dragonhydra.__file__).resolve().is_relative_to(site)
        for obj,name in ((local_ai,'infer'),(Product,'__init__'),(Product,'connect'),(Store,'__init__'),(Store,'receipt'),(Store,'ingest'),(Transport,'__init__'),(Transport,'get'),(source_context,'by_id'),(source_context,'latest'),(source_context,'append'),(source_context,'recover'),(memory,'_schema')):
            guards.enter_context(patch.object(obj,name,forbidden))
        for module_name,class_name,methods in (('dragonhydra.local_ai_settings','Settings',('__init__','effective','public','put')),('dragonhydra.connectors.vault','Vault',('__init__','get','put','delete'))):
            module=sys.modules.get(module_name)
            if module is not None:
                for name in methods:
                    if hasattr(getattr(module,class_name),name):guards.enter_context(patch.object(getattr(module,class_name),name,forbidden))
                for name in ('protect_bytes','unprotect_bytes'):
                    if hasattr(module,name):guards.enter_context(patch.object(module,name,forbidden))
        class State:
            def report(self):
                return {'forbidden_operation_attempts':len(attempts),'sqlite3_definitions_imported':'sqlite3' in sys.modules,
                    'settings_definitions_imported':'dragonhydra.local_ai_settings' in sys.modules,
                    'vault_definitions_imported':'dragonhydra.connectors.vault' in sys.modules,
                    'optional_server_modules_imported':{name:name in sys.modules for name in ('fastapi','uvicorn','openpyxl','tzdata')},
                    'database_connected':False,'grounding_run':False,'API_started':False,'worker_started':False,'model_inference':False,'services_changed':False}
        state=State()
        yield state
        assert not attempts
        assert not any(name in sys.modules for name in ('fastapi','uvicorn','openpyxl','tzdata'))
    sys.meta_path.remove(finder)
