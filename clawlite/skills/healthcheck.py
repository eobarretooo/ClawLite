from __future__ import annotations

from clawlite.skills._safe_exec import parse_command, safe_run, require_bin

SKILL_NAME = "healthcheck"
SKILL_DESCRIPTION = 'Track water and sleep with JSON file storage'


def run(command: str = "") -> str:
    """Executa a skill de forma segura (sem shell=True)."""
    if not command:
        return f"{SKILL_NAME} pronta. {SKILL_DESCRIPTION}"
    try:
        args = parse_command(command)
    except ValueError as exc:
        return str(exc)
    return safe_run(args)


def info() -> str:
    return '---\nname: healthcheck\ndescription: Track water and sleep with JSON file storage\nversion: 1.0.2\ntags: health, tracking\n---\n# Health Tracker\nSimple tracking for water intake and sleep using JSON file.\n## Data Format\nFile: `{baseDir}/health-data.json`\n```json\n{\n  "water": [{"time": "ISO8601", "cups": 2}],\n  "sleep": [{"time": "ISO8601", "action": "sleep|wake"}]\n}\n```\n## Add Water Record\nWhen user says "uống X cốc" or "uống nước X cốc":\n```bash\nnode -e "const fs=require(\'fs\');const f=\'{baseDir}/health-data.json\';let d={water:[],sleep:[]};try{d=JSON.parse(fs.readFileSync(f))}catch(e){}d.water.push({time:new Date().toISOString(),cups:CUPS});fs.writeFileSync(f,JSON.stringify(d));console.log(\'Da ghi: \'+CUPS+\' coc\')"\n```\nReplace `CUPS` with number from user input.\n## Add Sleep Record\nWhen user says "đi ngủ":\n```bash\nnode -e "const fs=require(\'fs\');const f=\'{baseDir}/health-data.json\';let d={water:[],sleep:[]};try{d=JSON.parse(fs.readFileSync(f))}catch(e){}d.sleep.push({time:new Date().toISOString(),action:\'sleep\'});fs.writeFileSync(f,JSON.stringify(d));console.log(\'Da ghi: di ngu\')"\n```\n## Add Wake Record\nWhen user says "thức dậy" or "dậy rồi":\n```bash\nnode -e "const fs=require(\'fs\');const f=\'{baseDir}/health-data.json\';let d={water:[],sleep:[]};try{d=JSON.parse(fs.readFileSync(f))}catch(e){}const last=d.sleep.filter(s=>s.action===\'sleep\').pop();d.sleep.push({time:new Date().toISOString(),action:\'wake\'});fs.writeFileSync(f,JSON.stringify(d));if(last){const h=((new Date()-new Date(last'
