from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path
from statistics import mean, median


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(0.95 * (len(s) - 1)))))
    return s[idx]


def main() -> int:
    # Isola validação em HOME temporário para não sujar runtime real
    home = Path('/tmp/clawlite-item5-home')
    if home.exists():
        import shutil

        shutil.rmtree(home)
    home.mkdir(parents=True, exist_ok=True)
    os.environ['HOME'] = str(home)

    # Importa após HOME definido (DB_PATH usa Path.home())
    from clawlite.runtime import multiagent as ma
    from clawlite.runtime.telegram_multiagent import dispatch_local

    cfg_dir = home / '.clawlite'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / 'telegram.multiagent.json'
    cfg = {
        'telegram': {
            'enabled': True,
            'token': 'MOCK_TOKEN',
            'defaultLabel': 'general',
            'routing': {
                'general': {'commandTemplate': 'mock'},
                'code': {'commandTemplate': 'mock'},
                'ops': {'commandTemplate': 'mock'},
            },
        }
    }
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')

    ma.init_db()

    py = sys.executable
    cmd_tpl = (
        f"{py} -c \"import sys,time; time.sleep(0.03); print('ok:'+sys.argv[1])\" "
        '"{label}:{text}"'
    )

    worker_ids = {}
    for label in ('general', 'code', 'ops'):
        wid = ma.upsert_worker('telegram', '10001', 'suporte', label, cmd_tpl, enabled=True)
        ma.start_worker(wid)
        worker_ids[label] = wid

    # Simulação mockada de 30 minutos de uso contínuo (eventos a cada 10s => 180 eventos)
    simulated_minutes = 30
    events = []
    labels = ['general', 'code', 'ops']
    for i in range(simulated_minutes * 6):
        label = labels[i % len(labels)]
        text = f'mensagem_{i:03d}_janela30m'
        events.append((label, text))

    enqueue_start = time.time()
    task_ids = []
    for i, (label, text) in enumerate(events):
        tid = dispatch_local(str(cfg_path), chat_id='10001', thread_id='suporte', label=label, text=text)
        task_ids.append(tid)

        # Teste de recuperação automática no meio da execução
        if i == 90:
            code_wid = worker_ids['code']
            code_row = next((w for w in ma.list_workers() if w.id == code_wid), None)
            if code_row and code_row.pid:
                try:
                    os.kill(code_row.pid, signal.SIGTERM)
                except OSError:
                    pass
            time.sleep(0.2)
            ma.recover_workers()

    enqueue_end = time.time()

    # Aguarda dreno da fila
    timeout_s = 120
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with sqlite3.connect(ma.DB_PATH) as c:
            queued = c.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'").fetchone()[0]
            running = c.execute("SELECT COUNT(*) FROM tasks WHERE status='running'").fetchone()[0]
        if queued == 0 and running == 0:
            break
        time.sleep(0.2)

    # Métricas
    with sqlite3.connect(ma.DB_PATH) as c:
        total = c.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        done = c.execute("SELECT COUNT(*) FROM tasks WHERE status='done'").fetchone()[0]
        failed = c.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0]
        rows = c.execute(
            "SELECT created_at, updated_at FROM tasks WHERE status IN ('done','failed') ORDER BY id"
        ).fetchall()

    latencies = [max(0.0, r[1] - r[0]) for r in rows]
    throughput = done / max(1e-9, (enqueue_end - enqueue_start))

    # Finaliza workers
    for wid in worker_ids.values():
        try:
            ma.stop_worker(wid)
        except Exception:
            pass

    report = {
        'simulated_window_minutes': simulated_minutes,
        'events': len(events),
        'enqueue_wall_seconds': round(enqueue_end - enqueue_start, 3),
        'tasks_total': total,
        'tasks_done': done,
        'tasks_failed': failed,
        'success_rate_pct': round((done / total) * 100, 2) if total else 0.0,
        'latency_avg_s': round(mean(latencies), 4) if latencies else 0.0,
        'latency_median_s': round(median(latencies), 4) if latencies else 0.0,
        'latency_p95_s': round(p95(latencies), 4) if latencies else 0.0,
        'enqueue_throughput_tps': round(throughput, 2),
        'db_path': str(ma.DB_PATH),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
