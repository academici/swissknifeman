"""Real MCP stdio exchange and protocol failure cleanup."""

import pytest

from skm.adapters.research.mcp_stdio import McpStdioResearchSource
from skm.adapters.research.retry import SourceFailed
from skm.kernel.cancel import Cancelled, CancelSource

from ._support import command, query

SERVER = """import json,sys
init=json.loads(sys.stdin.readline())
assert init['method']=='initialize' and init['id']==1
assert init['params']['protocolVersion']=='2024-11-05'
print(json.dumps({'jsonrpc':'2.0','id':1,'result':{'protocolVersion':'2024-11-05','capabilities':{},'serverInfo':{'name':'fixture','version':'1'}}}),flush=True)
notice=json.loads(sys.stdin.readline())
assert notice['method']=='notifications/initialized' and 'id' not in notice
call=json.loads(sys.stdin.readline())
assert call['method']=='tools/call' and call['params']['name']=='lookup'
assert call['params']['arguments']['query']=='research'
print(json.dumps({'jsonrpc':'2.0','method':'notifications/message','params':{}}),flush=True)
document={'origin':'mcp:fixture/docs','title':'MCP','text':'research evidence'}
result={'content':[{'type':'text','text':json.dumps({'documents':[document]})}]}
print(json.dumps({'jsonrpc':'2.0','id':2,'result':result}),flush=True)
sys.stdin.read()
"""


def test_mcp_initialize_notification_tool_query_and_cleanup():
    result = McpStdioResearchSource().search(
        command(SERVER, kind="mcp_stdio", tool="lookup"), query(), cancel=CancelSource().token
    )
    assert result.documents[0].origin == "mcp:fixture/docs"
    assert result.documents[0].text == "research evidence"


@pytest.mark.parametrize("replacement", ["'id':3", "'id':True", "'id':None"])
def test_mcp_rejects_unmatched_response_ids(replacement):
    server = SERVER.replace("'id':2", replacement)
    with pytest.raises(SourceFailed):
        McpStdioResearchSource().search(
            command(server, kind="mcp_stdio", tool="lookup"), query(), cancel=CancelSource().token
        )


def test_mcp_shared_cancel_never_starts_a_process():
    cancel = CancelSource()
    cancel.cancel("shutdown")
    with pytest.raises(Cancelled, match="shutdown"):
        McpStdioResearchSource().search(
            command(SERVER, kind="mcp_stdio", tool="lookup"), query(), cancel=cancel.token
        )
