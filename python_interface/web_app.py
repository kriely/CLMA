"""
CLMA Web UI - Flask-based interactive interface for the Closed-Loop Multi-Agent Framework.
"""
import os
import sys
import json
import threading
APP_VERSION = 'v25'
from flask import Flask, render_template, request, jsonify, stream_with_context, Response, send_file

# Ensure we can find our package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import CLMAFramework
from tool_executor import ToolExecutor
from api_providers import (
    load_config, save_config, get_available_providers,
    create_provider, PROVIDER_DEFAULTS, PROVIDER_MODELS,
)
# LLM Catalog (dynamic provider directory)
import copy as _copy

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Disable static file caching entirely — the app.js evolves rapidly
# during debugging and aggressive browser caching caused persistent
# "sidebar not updating" bugs that wasted hours of debugging.
# Long story short: no cache, fresh every time.
@app.after_request
def _add_no_cache(response):
    if response.content_type and ('text/html' in response.content_type or
                                   'javascript' in response.content_type or
                                   'text/css' in response.content_type or
                                   'application/json' in response.content_type):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Global framework instance
framework = None
framework_lock = threading.Lock()


def get_framework():
    """Lazy initialize the framework singleton."""
    global framework
    if framework is None:
        with framework_lock:
            if framework is None:
                framework = CLMAFramework()
    return framework


# ===== Page Routes =====

@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


@app.route('/plugins')
def plugins_page():
    """Render plugin management page."""
    return render_template('plugins.html')


# ===== Query Pipeline =====

@app.route('/api/status')
def api_status():
    """Get framework status."""
    fw = get_framework()
    cfg = load_config()
    return jsonify({
        'status': 'ready',
        'mode': fw.get_mode(),
        'stats': fw.get_statistics(),
        'rules': len(fw.get_rules()),
        'api_configured': fw.api_configured,
        'api_provider': cfg.get('provider', 'none') if cfg.get('enabled') else None,
    })


@app.route('/api/process', methods=['POST'])
def api_process():
    """Process a query through the multi-agent pipeline."""
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Query cannot be empty'}), 400

    fw = get_framework()
    result = fw.process_query(query)
    stats = fw.get_statistics()
    history = fw.get_execution_history()
    mode = fw.get_mode()
    # Include tool results from the framework if available
    tool_results = getattr(fw, '_tool_results', [])

    return jsonify({
        'query': query,
        'result': result,
        'stats': stats,
        'history': history,
        'mode': mode,
        'tool_results': [tr.to_dict() if hasattr(tr, 'to_dict') else tr for tr in tool_results],
    })


@app.route('/api/history')
def api_history():
    """Get execution history."""
    fw = get_framework()
    return jsonify({
        'history': fw.get_execution_history(),
    })


# ===== Settings =====

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get or update settings."""
    fw = get_framework()
    if request.method == 'POST':
        data = request.get_json()
        if 'mode' in data:
            fw.set_mode(data['mode'])
        if 'max_iterations' in data:
            fw.set_max_iterations(int(data['max_iterations']))
        if 'threshold' in data:
            fw.set_threshold(float(data['threshold']))
        if 'execution_timeout' in data:
            fw.set_execution_timeout(int(data['execution_timeout']))
        if 'token_budget' in data:
            fw.set_token_budget(int(data['token_budget']))
        if 'reset' in data and data['reset']:
            fw.reset()
        if 'dag_enabled' in data:
            fw.set_dag_mode(bool(data['dag_enabled']))
        if 'dag_mode' in data:
            fw.set_dag_mode(bool(data['dag_mode']))
        if 'arch_mode' in data:
            fw.set_arch_mode(str(data['arch_mode']))
        return jsonify({
            'status': 'updated',
            'mode': fw.get_mode(),
            'max_iterations': fw._max_iterations if hasattr(fw, '_max_iterations') else 2,
            'threshold': fw._threshold if hasattr(fw, '_threshold') else 0.75,
            'execution_timeout': fw._execution_timeout if hasattr(fw, '_execution_timeout') else 120,
            'token_budget': fw._token_budget if hasattr(fw, '_token_budget') else 10000,
            'dag_mode': fw.orchestrator.is_dag_mode(),
            'arch_mode': fw.get_arch_mode(),
        })

    return jsonify({
        'mode': fw.get_mode(),
        'max_iterations': fw._max_iterations if hasattr(fw, '_max_iterations') else 2,
        'threshold': fw._threshold if hasattr(fw, '_threshold') else 0.75,
        'execution_timeout': fw._execution_timeout if hasattr(fw, '_execution_timeout') else 120,
        'token_budget': fw._token_budget if hasattr(fw, '_token_budget') else 10000,
        'usage_ratio': fw.get_statistics()['usage_ratio'],
        'dag_mode': fw.orchestrator.is_dag_mode(),
        'arch_mode': fw.get_arch_mode(),
    })


# ===== API Configuration =====

@app.route('/api/api-config', methods=['GET', 'POST'])
def api_api_config():
    """Get or update LLM API configuration."""
    if request.method == 'POST':
        data = request.get_json()
        # Whitelist keys
        allowed = {'provider', 'api_key', 'model', 'base_url',
                   'temperature', 'max_tokens', 'enabled'}
        config = {k: data[k] for k in allowed if k in data}
        # Auto-fill missing base_url and model from defaults
        provider = config.get('provider', '')
        defaults = PROVIDER_DEFAULTS.get(provider, {})
        if 'base_url' not in config and 'base_url' in defaults:
            config['base_url'] = defaults['base_url']
        if 'model' not in config and 'model' in defaults:
            config['model'] = defaults['model']
        save_config(config)
        # Reload provider in framework
        get_framework().refresh_api_config()
        return jsonify({'status': 'saved'})

    config = load_config()
    # Return masked api_key for display, keep original in 'api_key_masked'
    key = config.get('api_key', '')
    config['api_key_masked'] = key[:8] + '...' + key[-4:] if len(key) > 12 else ''
    # Also return api_key so frontend can send it back when saving
    # (frontend never modifies the key field unless user types a new one)
    return jsonify(config)


# === LLM Provider Catalog ===

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config", "llm_catalog.json")


def _load_catalog():
    """Load LLM provider catalog from disk."""
    if not os.path.exists(CATALOG_PATH):
        return {"providers": {}, "categories": {}, "api_types": {}}
    try:
        with open(CATALOG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"providers": {}, "categories": {}, "api_types": {}}


@app.route('/api/llm-catalog')
def api_llm_catalog():
    """Get the full LLM provider catalog (dynamic directory).
    Returns all providers, categories, API types, and vendor metadata.
    Used by the frontend to dynamically render provider selection UI.
    """
    catalog = _load_catalog()
    # Also return current selection from config
    config = load_config()
    return jsonify({
        'catalog': catalog,
        'current': {
            'provider': config.get('provider', ''),
            'model': config.get('model', ''),
            'api_key': config.get('api_key', ''),
            'api_key_masked': config.get('api_key', '')[:8] + '...' + config.get('api_key', '')[-4:]
                if len(config.get('api_key', '')) > 12 else '',
            'base_url': config.get('base_url', ''),
            'temperature': config.get('temperature', 0.7),
            'max_tokens': config.get('max_tokens', 8192),
            'enabled': config.get('enabled', False),
        },
    })


# (legacy endpoint kept for backward compat — frontend now uses /api/llm-catalog)
@app.route('/api/api-config/providers')
def api_providers_list():
    """Get available providers with metadata."""
    return jsonify({
        'providers': get_available_providers(),
        'defaults': PROVIDER_DEFAULTS,
        'models': PROVIDER_MODELS,
    })


@app.route('/api/api-config/test', methods=['POST'])
def api_test_connection():
    """Test the current API configuration."""
    data = request.get_json()
    # Merge with saved config (so partial updates work)
    saved = load_config()
    saved.update(data)
    # Fix: if base_url not explicitly provided in request (partial update),
    # use the correct default for the provider — don't let stale saved value leak
    if 'base_url' not in data:
        saved['base_url'] = PROVIDER_DEFAULTS.get(saved.get('provider', ''), {}).get('base_url', '')
    # Also fix model if not explicitly provided
    if 'model' not in data:
        saved['model'] = PROVIDER_DEFAULTS.get(saved.get('provider', ''), {}).get('model', '')
    try:
        provider = create_provider(saved)
        if provider is None:
            return jsonify({'success': False, 'message': 'API not enabled. Enable and set an API key first.'})
        success, msg = provider.test_connection()
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)[:200]})


# ===== Rules Management =====

@app.route('/api/rules', methods=['GET', 'POST'])
def api_rules():
    """Get or update rules."""
    fw = get_framework()
    if request.method == 'POST':
        data = request.get_json()
        if 'rules' in data:
            fw.save_rules(data['rules'])
            return jsonify({'status': 'saved', 'count': len(data['rules'])})
        return jsonify({'error': 'No rules provided'}), 400

    return jsonify({
        'rules': fw.get_rules(),
    })


@app.route('/api/rules/template')
def api_rules_template():
    """Get a rule template for reference."""
    return jsonify({
        'template': {
            "pattern": "your_regex_pattern",
            "validation_method": "code_generation|analysis|execution|refactoring",
            "recommended_tools": ["tool1", "tool2"],
            "weights": {
                "reasonableness": 0.4,
                "executability": 0.4,
                "satisfaction": 0.2
            },
            "threshold": 0.7
        },
        'examples': [
            {
                "pattern": "write|create|generate",
                "validation_method": "code_generation",
                "recommended_tools": ["compiler", "interpreter"],
                "weights": {"reasonableness": 0.4, "executability": 0.4, "satisfaction": 0.2},
                "threshold": 0.7,
                "description": "Code generation tasks"
            },
            {
                "pattern": "explain|analyze|debug",
                "validation_method": "analysis",
                "recommended_tools": ["debugger", "profiler"],
                "weights": {"reasonableness": 0.5, "executability": 0.3, "satisfaction": 0.2},
                "threshold": 0.7,
                "description": "Analysis and debugging tasks"
            },
            {
                "pattern": "deploy|build|run",
                "validation_method": "execution",
                "recommended_tools": ["docker", "shell"],
                "weights": {"reasonableness": 0.3, "executability": 0.5, "satisfaction": 0.2},
                "threshold": 0.7,
                "description": "Execution and deployment tasks"
            },
        ],
    })


# ===== SSE Streaming =====

@app.route('/api/process/stream')
def api_process_stream():
    """SSE streaming endpoint for real-time agent processing."""
    query = request.args.get('query', '').strip()
    # URL 编码中 + 号会被解码为空格，但代码查询中的 + 号（如 1+1）应保留
    # 如果原始 query 包含 + 号的常见模式，还原它
    if query and '+' not in query:
        # 只在 query 看起来像代码/数学表达式时才还原
        import re as _qr
        if _qr.search(r'\d \d|1 1| \d\+', query):
            query = query.replace(' ', '+', 1)
    if not query:
        return jsonify({'error': 'Query required'}), 400

    fw = get_framework()

    def generate():
        for event in fw.process_query_stream(query):
            # Auto-save session BEFORE yielding done event, so that
            # frontend's refreshSessionList() immediately sees the new session
            # and can highlight it correctly in the sidebar.
            if event['event'] == 'done':
                try:
                    # Ensure minimal stats fields for frontend (compatible with all modes)
                    stats = event.get('stats', {})
                    if 'queries_processed' not in stats:
                        stats['queries_processed'] = stats.get('total_iterations', 0) or 1
                    if 'iterations_executed' not in stats:
                        stats['iterations_executed'] = stats.get('total_iterations', 0) or 1
                    if 'rules_matched' not in stats:
                        stats['rules_matched'] = 1
                    if 'processes_completed' not in stats:
                        stats['processes_completed'] = 1
                    if 'token_budget' not in stats:
                        stats['token_budget'] = fw.token_monitor.get_budget() if hasattr(fw, 'token_monitor') else 10000
                    event['stats'] = stats

                    sid = event.get('session_id', '')
                    result = event.get('result', {})
                    # Include history in result so it gets persisted with the session
                    history = event.get('history', [])
                    if history and isinstance(result, dict):
                        result = dict(result)
                        result['_saved_history'] = history
                    scores = result.get('score', {})
                    stats = event.get('stats', {})
                    mode = event.get('mode', 'closed')
                    import logging as _lg3
                    _lg3.info(f"[TRACE_ADD_MSG] result keys: {list(result.keys()) if isinstance(result, dict) else 'not dict'}")
                    _lg3.info(f"[TRACE_ADD_MSG] sandbox_files in result: {result.get('sandbox_files', 'NO') if isinstance(result, dict) else 'N/A'}")
                    add_message(
                        session_id=sid,
                        query=query,
                        result=result,
                        scores=scores,
                        stats=stats,
                        mode=mode,
                    )
                except Exception as e:
                    import logging as _lg4
                    _lg4.exception(f"[TRACE_ADD_MSG] EXCEPTION in add_message: {e}")
            yield f"event: {event['event']}\ndata: {json.dumps(event)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/process/cancel', methods=['POST'])
def api_process_cancel():
    """Cancel the currently running SSE stream (if any).
    
    Sets _stream_cancelled on the framework instance. The generator
    checks this flag between agent calls and yields a done event
    with partial results immediately.
    """
    fw = get_framework()
    fw._stream_cancelled = True
    return jsonify({'status': 'cancelled', 'message': 'Stream cancellation requested'})


@app.route('/api/health')
def api_health():
    """Simple health check for frontend connectivity testing."""
    return jsonify({'status': 'ok'})


# ===== Session Management =====

from session_store import (
    list_sessions, list_sessions_grouped, create_session, get_session,
    delete_session, rename_session, add_message, delete_sessions_by_date,
)


@app.route('/api/sessions', methods=['GET', 'POST'])
def api_sessions():
    """List sessions (GET) or create a new session (POST)."""
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', 'New Session')
        session = create_session(name)
        resp = jsonify(session)
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp, 201

    limit = request.args.get('limit', 200, type=int)
    grouped = list_sessions_grouped(limit=limit)
    resp = jsonify(grouped)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/api/sessions/group/<date_key>', methods=['DELETE'])
def api_delete_group(date_key):
    """Delete all sessions in a date group (e.g. '2026-05-03')."""
    deleted = delete_sessions_by_date(date_key)
    return jsonify({'status': 'deleted', 'count': deleted})


@app.route('/api/sessions/<session_id>', methods=['GET', 'DELETE', 'PATCH'])
def api_session_detail(session_id):
    """Get, delete, or rename a session."""
    if request.method == 'DELETE':
        ok = delete_session(session_id)
        if not ok:
            return jsonify({'error': 'Session not found'}), 404
        return jsonify({'status': 'deleted'})

    if request.method == 'PATCH':
        data = request.get_json() or {}
        if 'name' in data:
            session = rename_session(session_id, data['name'])
            if session is None:
                return jsonify({'error': 'Session not found'}), 404
            return jsonify(session)
        return jsonify({'error': 'No valid fields to update'}), 400

    session = get_session(session_id)
    if session is None:
        return jsonify({'error': 'Session not found'}), 404
    return jsonify(session)


# ===== Stats =====

@app.route('/api/stats')
def api_stats():
    """Get detailed statistics."""
    fw = get_framework()
    stats = fw.get_statistics()
    stats['token_by_agent'] = fw.get_token_usage_by_agent()
    stats['token_by_operation'] = fw.get_token_usage_by_operation()
    return jsonify(stats)


# ===== Tool Execution =====

# Global tool executor instance
_tool_executor = None
_tool_lock = threading.Lock()


def get_tool_executor():
    """Lazy initialize the tool executor singleton.
    Uses the same sandbox directory as the CLMA engine (tools/sandbox/)."""
    global _tool_executor
    if _tool_executor is None:
        with _tool_lock:
            if _tool_executor is None:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                sandbox_dir = os.path.join(base_dir, "tools", "sandbox")
                _tool_executor = ToolExecutor(sandbox_dir=sandbox_dir)
    return _tool_executor


@app.route('/api/tools/status')
def api_tools_status():
    """Get tool executor capabilities and sandbox info."""
    te = get_tool_executor()
    caps = te.get_capabilities()
    sandbox_path = te.get_sandbox_path()
    # List sandbox files
    files_res = te.list_files(".")
    sandbox_files = []
    if files_res.success and files_res.stdout.strip():
        sandbox_files = [f.strip() for f in files_res.stdout.strip().split('\n') if f.strip()]
    return jsonify({
        'sandbox_path': sandbox_path,
        'capabilities': caps,
        'file_count': len(sandbox_files),
        'files': sandbox_files[:50],
    })


@app.route('/api/tools/execute', methods=['POST'])
def api_tools_execute():
    """Execute arbitrary code in the sandbox."""
    data = request.get_json()
    code = (data.get('code') or '').strip()
    language = (data.get('language') or 'python').strip().lower()
    if not code:
        return jsonify({'error': 'Code cannot be empty'}), 400

    te = get_tool_executor()
    try:
        result = te.execute_code(code, language=language)
        return jsonify({
            'tool_name': result.tool_name,
            'success': result.success,
            'exit_code': result.exit_code,
            'stdout': result.stdout if result.stdout else '',
            'stderr': result.stderr if result.stderr else '',
            'duration_ms': result.duration_ms,
            'input_summary': result.input_summary,
        })
    except Exception as e:
        return jsonify({'error': str(e)[:500], 'success': False, 'tool_name': language}), 500


@app.route('/api/tools/sandbox/clean', methods=['POST'])
def api_tools_sandbox_clean():
    """Reset/clean the sandbox directory."""
    te = get_tool_executor()
    te.reset_sandbox()
    return jsonify({'status': 'cleaned', 'sandbox_path': te.get_sandbox_path()})


@app.route('/api/tools/sandbox/files')
def api_tools_sandbox_files():
    """List files in the sandbox directory."""
    te = get_tool_executor()
    result = te.list_files(".")
    if not result.success:
        return jsonify({'files': [], 'error': result.stderr})
    files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
    return jsonify({'files': files, 'count': len(files), 'sandbox_path': te.get_sandbox_path()})


@app.route('/api/tools/sandbox/read')
def api_tools_sandbox_read():
    """Read a file from the sandbox directory."""
    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'path parameter required'}), 400
    # Normalize: strip leading ./ if present
    path = path.lstrip('./')
    te = get_tool_executor()
    result = te.read_file(path)
    if not result.success:
        return jsonify({'error': result.stderr}), 404
    return jsonify({
        'path': path,
        'content': result.stdout,
        'size': len(result.stdout),
    })


@app.route('/api/tools/sandbox/download')
def api_tools_sandbox_download():
    """Download a single file from the sandbox."""
    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'path parameter required'}), 400
    path = path.lstrip('./')
    te = get_tool_executor()
    safe_path = te._resolve_sandbox_path(path)
    if safe_path is None or not os.path.isfile(safe_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        safe_path,
        as_attachment=True,
        download_name=os.path.basename(path),
    )


@app.route('/api/tools/sandbox/download-all')
def api_tools_sandbox_download_all():
    """Download the entire sandbox as a ZIP archive."""
    import io, zipfile
    te = get_tool_executor()
    sandbox = te._sandbox_dir
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, fnames in os.walk(sandbox):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for fname in fnames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, sandbox)
                zf.write(full, rel)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype='application/zip',
        headers={'Content-Disposition': 'attachment; filename=sandbox.zip'},
    )


@app.route('/api/tools/docker/info')
def api_tools_docker_info():
    """Get Docker availability and info."""
    te = get_tool_executor()
    result = te.docker_info()
    return jsonify({
        'docker_available': te.is_docker_available(),
        'info': result.stdout[-2048:] if result.success else result.stderr[-512:],
    })


# ===== Plugin Management =====


def _plugin_info_to_dict(info):
    """Convert a C++ PluginInfo to a JSON-serializable dict."""
    return {
        'id': info.id,
        'name': info.name,
        'version': info.version.to_string(),
        'version_major': info.version.major,
        'version_minor': info.version.minor,
        'version_patch': info.version.patch,
        'type': _plugin_type_name(info.type),
        'type_code': int(info.type),
        'author': info.author,
        'description': info.description,
        'dependencies': list(info.dependencies),
        'license': info.license,
        'api_version': info.api_version,
    }


def _plugin_type_name(t):
    """Map PluginType enum to human-readable name."""
    import clma_core
    mapping = {
        clma_core.PluginType.TOOL: 'tool',
        clma_core.PluginType.STRATEGY: 'strategy',
        clma_core.PluginType.JUDGE: 'judge',
        clma_core.PluginType.PROVIDER: 'provider',
        clma_core.PluginType.CUSTOM: 'custom',
    }
    return mapping.get(t, 'unknown')


def _plugin_state_name(s):
    """Map PluginState enum to human-readable name."""
    import clma_core
    mapping = {
        clma_core.PluginState.UNLOADED: 'unloaded',
        clma_core.PluginState.LOADED: 'loaded',
        clma_core.PluginState.INITIALIZED: 'initialized',
        clma_core.PluginState.RUNNING: 'running',
        clma_core.PluginState.ERROR: 'error',
        clma_core.PluginState.UNLOADING: 'unloading',
    }
    return mapping.get(s, 'unknown')


@app.route('/api/plugins/scan')
def api_plugins_scan():
    """Scan plugin directories for new plugins."""
    fw = get_framework()
    pm = fw.plugin_manager
    before = pm.get_plugin_count()
    pm.scan_plugins()
    after = pm.get_plugin_count()
    return jsonify({
        'before': before,
        'after': after,
        'new': after - before,
        'directories': pm.get_plugin_directories(),
    })


@app.route('/api/plugins')
def api_plugins():
    """Get list of all discovered plugins with current state."""
    fw = get_framework()
    pm = fw.plugin_manager

    # Discover available plugins from directories
    pm.scan_plugins()

    plugins = pm.list_plugins()
    result = []
    for info in plugins:
        entry = _plugin_info_to_dict(info)
        entry['state'] = _plugin_state_name(pm.get_plugin_state(info.id))
        entry['loaded'] = pm.is_plugin_loaded(info.id)
        result.append(entry)

    return jsonify({
        'plugins': result,
        'count': len(result),
        'directories': pm.get_plugin_directories(),
        'loaded_count': pm.get_plugin_count(),
    })


@app.route('/api/plugins/<plugin_id>')
def api_plugin_detail(plugin_id):
    """Get detailed info for a single plugin."""
    fw = get_framework()
    pm = fw.plugin_manager

    plugins = pm.list_plugins()
    target = None
    for info in plugins:
        if info.id == plugin_id:
            target = info
            break

    if target is None:
        return jsonify({'error': f'Plugin "{plugin_id}" not found'}), 404

    entry = _plugin_info_to_dict(target)
    entry['state'] = _plugin_state_name(pm.get_plugin_state(plugin_id))
    entry['loaded'] = pm.is_plugin_loaded(plugin_id)
    entry['dependents'] = list(pm.get_plugin_dependents(plugin_id))
    entry['dependencies_tree'] = list(pm.get_plugin_dependencies(plugin_id))

    return jsonify({'plugin': entry})


@app.route('/api/plugins/<plugin_id>/toggle', methods=['POST'])
def api_plugin_toggle(plugin_id):
    """Start or stop a plugin based on its current state."""
    fw = get_framework()
    pm = fw.plugin_manager

    if not pm.is_plugin_loaded(plugin_id):
        return jsonify({'error': f'Plugin "{plugin_id}" not loaded'}), 400

    state = pm.get_plugin_state(plugin_id)
    if state == clma_core.PluginState.RUNNING:
        ok = pm.stop_plugin(plugin_id)
        action = 'stopped'
    elif state == clma_core.PluginState.INITIALIZED:
        ok = pm.start_plugin(plugin_id)
        action = 'started'
    elif state == clma_core.PluginState.LOADED:
        ok = pm.initialize_plugin(plugin_id) and pm.start_plugin(plugin_id)
        action = 'started'
    elif state == clma_core.PluginState.ERROR:
        ok = pm.attempt_recovery(plugin_id)
        action = 'recovered'
    else:
        return jsonify({'error': f'Plugin "{plugin_id}" in state {_plugin_state_name(state)}, cannot toggle'}), 400

    return jsonify({
        'success': ok,
        'action': action,
        'plugin_id': plugin_id,
        'state': _plugin_state_name(pm.get_plugin_state(plugin_id)),
    })


@app.route('/api/plugins/<plugin_id>/hot-reload', methods=['POST'])
def api_plugin_hot_reload(plugin_id):
    """Hot-reload a plugin."""
    fw = get_framework()
    pm = fw.plugin_manager

    if not pm.is_plugin_loaded(plugin_id):
        return jsonify({'error': f'Plugin "{plugin_id}" not loaded'}), 400

    ok = pm.hot_reload(plugin_id)
    return jsonify({
        'success': ok,
        'plugin_id': plugin_id,
        'state': _plugin_state_name(pm.get_plugin_state(plugin_id)),
    })


@app.route('/api/plugins/<plugin_id>/recover', methods=['POST'])
def api_plugin_recover(plugin_id):
    """Attempt to recover an errored plugin."""
    fw = get_framework()
    pm = fw.plugin_manager

    state = pm.get_plugin_state(plugin_id)
    if state != clma_core.PluginState.ERROR:
        return jsonify({
            'success': True,
            'message': f'Plugin "{plugin_id}" is not in ERROR state (current: {_plugin_state_name(state)})',
            'plugin_id': plugin_id,
            'state': _plugin_state_name(state),
        })

    ok = pm.attempt_recovery(plugin_id)
    return jsonify({
        'success': ok,
        'plugin_id': plugin_id,
        'state': _plugin_state_name(pm.get_plugin_state(plugin_id)),
    })


if __name__ == '__main__':
    print("""
  ╔══════════════════════════════════════════════════╗
  ║   CLMA Framework - Web Interface                 ║
  ║   Closed-Loop Multi-Agent Reasoning System       ║
  ╚══════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
