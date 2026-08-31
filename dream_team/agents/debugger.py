"""Dream Team — Debugger Agent (System Doctor)
Monitors system health, diagnoses errors with LLM assistance, scans logs
for patterns, attempts automatic fixes, and manages log retention.
"""
import glob
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from dream_team import config
from dream_team.base_agent import BaseAgent
from dream_team.memory import SharedMemory

logger = logging.getLogger("dreamteam.debugger")

# Known issue patterns that auto_fix can handle
_KNOWN_FIXES = {
    "temp_files": {
        "patterns": ["temp", "temporary", "tmp", "disk space", "no space"],
        "description": "Clear temporary files",
    },
    "ollama_restart": {
        "patterns": ["ollama", "llm", "model", "inference", "connection refused"],
        "description": "Restart Ollama service",
    },
    "missing_dirs": {
        "patterns": ["directory", "folder", "not found", "no such file", "mkdir", "path"],
        "description": "Recreate missing directories",
    },
}


class Debugger(BaseAgent):
    """System Doctor agent.

    Provides health monitoring, error diagnosis (LLM-powered), log analysis,
    automatic remediation for known issues, and log retention management.
    """

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(
            name="debugger",
            description="System Doctor — monitors health, diagnoses errors, auto-fixes issues",
            agent_config=config.DEBUGGER_CONFIG,
        )
        self.memory = memory
        self._error_history: List[Dict[str, Any]] = []
        self.logger.info(
            "Debugger initialised — auto_fix=%s, alerts=%s, retention=%dd",
            self.agent_config.get("auto_fix", True),
            self.agent_config.get("alert_on_errors", True),
            self.agent_config.get("log_retention_days", 30),
        )

    # ──────────────────────────────────────────────────────────────────
    # Error diagnosis
    # ──────────────────────────────────────────────────────────────────

    def diagnose_error(self, error_msg: str, context: str = "") -> dict:
        """Analyse an error message using the LLM and return a diagnosis.

        Args:
            error_msg: The error string to diagnose.
            context: Optional surrounding context (traceback, config, etc.).

        Returns:
            {
                "diagnosis": str,
                "severity": "low" | "medium" | "high" | "critical",
                "suggested_fix": str,
                "auto_fixable": bool,
            }
        """
        self.logger.info("diagnose_error() — msg length=%d, context length=%d", len(error_msg), len(context))

        prompt = (
            "You are a senior DevOps engineer diagnosing a system error.\n\n"
            f"Error message:\n{error_msg}\n\n"
        )
        if context:
            prompt += f"Additional context:\n{context}\n\n"

        prompt += (
            "Respond in JSON only (no markdown) with exactly these keys:\n"
            '  "diagnosis": a clear explanation of what went wrong\n'
            '  "severity": one of "low", "medium", "high", "critical"\n'
            '  "suggested_fix": a concrete step to resolve the issue\n'
            '  "auto_fixable": boolean — can this be fixed automatically?\n'
        )

        result = self._default_diagnosis(error_msg)

        try:
            raw = self.think(prompt, temperature=0.3, max_tokens=400)
            parsed = json.loads(raw)
            severity = parsed.get("severity", "medium")
            if severity not in ("low", "medium", "high", "critical"):
                severity = "medium"
            result = {
                "diagnosis": parsed.get("diagnosis", result["diagnosis"]),
                "severity": severity,
                "suggested_fix": parsed.get("suggested_fix", result["suggested_fix"]),
                "auto_fixable": bool(parsed.get("auto_fixable", False)),
            }
        except (json.JSONDecodeError, Exception) as exc:
            self.logger.warning("LLM diagnosis parse failed, using heuristic: %s", exc)

        # Record in history and shared memory
        error_record = {
            "error_msg": error_msg,
            "context": context,
            "diagnosis": result,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._error_history.append(error_record)

        # Keep local history bounded
        if len(self._error_history) > 200:
            self._error_history = self._error_history[-200:]

        try:
            mem_key = f"error_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
            self.memory.store(mem_key, error_record, category="errors", agent=self.name)
        except Exception as exc:
            self.logger.warning("Failed to persist error record: %s", exc)

        if self.agent_config.get("alert_on_errors", True) and result["severity"] in ("high", "critical"):
            self.logger.warning(
                "🚨 %s severity error diagnosed: %s", result["severity"].upper(), result["diagnosis"],
            )

        self.logger.info("Diagnosis complete — severity=%s, auto_fixable=%s", result["severity"], result["auto_fixable"])
        return result

    def _default_diagnosis(self, error_msg: str) -> dict:
        """Heuristic fallback diagnosis when LLM is unavailable."""
        msg_lower = error_msg.lower()

        severity = "medium"
        if any(kw in msg_lower for kw in ("critical", "fatal", "crash", "data loss", "corrupt")):
            severity = "critical"
        elif any(kw in msg_lower for kw in ("error", "failed", "exception", "refused")):
            severity = "high"
        elif any(kw in msg_lower for kw in ("warning", "timeout", "slow", "retry")):
            severity = "low"

        auto_fixable = any(
            any(p in msg_lower for p in fix_info["patterns"])
            for fix_info in _KNOWN_FIXES.values()
        )

        return {
            "diagnosis": f"Error detected: {error_msg[:200]}",
            "severity": severity,
            "suggested_fix": "Review the error details and check system logs for more context.",
            "auto_fixable": auto_fixable,
        }

    # ──────────────────────────────────────────────────────────────────
    # System health check
    # ──────────────────────────────────────────────────────────────────

    def check_system_health(self) -> dict:
        """Run health checks on critical system components.

        Checks:
            - Disk space availability
            - ffmpeg / ffprobe availability
            - Ollama server status
            - Database connectivity (SharedMemory)

        Returns:
            {
                "status": "healthy" | "degraded" | "critical",
                "checks": {<name>: {"ok": bool, "detail": str}, ...},
                "issues": list[str],
            }
        """
        self.logger.info("check_system_health() started")
        checks: Dict[str, Dict[str, Any]] = {}
        issues: List[str] = []

        # 1. Disk space
        checks["disk_space"] = self._check_disk_space()
        if not checks["disk_space"]["ok"]:
            issues.append(checks["disk_space"]["detail"])

        # 2. ffmpeg
        checks["ffmpeg"] = self._check_ffmpeg()
        if not checks["ffmpeg"]["ok"]:
            issues.append(checks["ffmpeg"]["detail"])

        # 3. Ollama
        checks["ollama"] = self._check_ollama()
        if not checks["ollama"]["ok"]:
            issues.append(checks["ollama"]["detail"])

        # 4. Database
        checks["database"] = self._check_database()
        if not checks["database"]["ok"]:
            issues.append(checks["database"]["detail"])

        # Determine overall status
        failed_count = sum(1 for c in checks.values() if not c["ok"])
        if failed_count == 0:
            status = "healthy"
        elif failed_count <= 2:
            status = "degraded"
        else:
            status = "critical"

        result = {"status": status, "checks": checks, "issues": issues}

        self.logger.info(
            "Health check complete — status=%s, issues=%d", status, len(issues),
        )
        return result

    def _check_disk_space(self) -> Dict[str, Any]:
        """Check available disk space on the project drive."""
        try:
            usage = shutil.disk_usage(str(config.DREAM_TEAM_DIR))
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            pct_free = (usage.free / usage.total) * 100

            if pct_free < 5:
                return {"ok": False, "detail": f"Critically low disk space: {free_gb:.1f}GB free ({pct_free:.1f}%)"}
            if pct_free < 15:
                return {"ok": True, "detail": f"Low disk space warning: {free_gb:.1f}GB free ({pct_free:.1f}%)"}
            return {"ok": True, "detail": f"{free_gb:.1f}GB free of {total_gb:.1f}GB ({pct_free:.1f}% free)"}
        except Exception as exc:
            return {"ok": False, "detail": f"Disk space check failed: {exc}"}

    def _check_ffmpeg(self) -> Dict[str, Any]:
        """Check if ffmpeg and ffprobe are available."""
        for tool in ("ffmpeg", "ffprobe"):
            try:
                result = subprocess.run(
                    [tool, "-version"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    return {"ok": False, "detail": f"{tool} returned non-zero exit code"}
            except FileNotFoundError:
                return {"ok": False, "detail": f"{tool} not found in PATH"}
            except subprocess.TimeoutExpired:
                return {"ok": False, "detail": f"{tool} timed out during version check"}
            except Exception as exc:
                return {"ok": False, "detail": f"{tool} check failed: {exc}"}

        return {"ok": True, "detail": "ffmpeg and ffprobe are available"}

    def _check_ollama(self) -> Dict[str, Any]:
        """Check if the Ollama server is responding."""
        if not config.USE_OLLAMA:
            return {"ok": True, "detail": "Ollama disabled in config — skipped"}
        try:
            resp = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "?") for m in models]
                return {"ok": True, "detail": f"Ollama online — {len(models)} models: {', '.join(model_names[:5])}"}
            return {"ok": False, "detail": f"Ollama returned HTTP {resp.status_code}"}
        except requests.ConnectionError:
            return {"ok": False, "detail": f"Cannot connect to Ollama at {config.OLLAMA_HOST}"}
        except Exception as exc:
            return {"ok": False, "detail": f"Ollama check failed: {exc}"}

    def _check_database(self) -> Dict[str, Any]:
        """Check SharedMemory database connectivity."""
        try:
            stats = self.memory.get_stats()
            total = stats.get("total", 0)
            return {"ok": True, "detail": f"Database OK — {total} entries across categories"}
        except Exception as exc:
            return {"ok": False, "detail": f"Database check failed: {exc}"}

    # ──────────────────────────────────────────────────────────────────
    # Log analysis
    # ──────────────────────────────────────────────────────────────────

    def analyze_logs(self, log_dir: str = None) -> dict:
        """Scan log files for error patterns and produce a summary.

        Args:
            log_dir: Path to scan. Defaults to ``dream_team/logs/``.

        Returns:
            {
                "total_errors": int,
                "error_types": {<type>: int, ...},
                "most_common": str,
                "recommendations": list[str],
            }
        """
        log_path = Path(log_dir) if log_dir else config.LOGS_DIR
        self.logger.info("analyze_logs() scanning: %s", log_path)

        if not log_path.exists() or not log_path.is_dir():
            self.logger.warning("Log directory does not exist: %s", log_path)
            return {
                "total_errors": 0,
                "error_types": {},
                "most_common": "N/A",
                "recommendations": [f"Log directory not found: {log_path}"],
            }

        error_types: Dict[str, int] = {}
        total_errors = 0

        # Scan all .log files in the directory
        log_files = list(log_path.glob("*.log"))
        if not log_files:
            return {
                "total_errors": 0,
                "error_types": {},
                "most_common": "N/A",
                "recommendations": ["No log files found. Agents may not have run yet."],
            }

        for log_file in log_files:
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line_upper = line.upper()
                        if "| ERROR |" in line_upper or "| CRITICAL |" in line_upper:
                            total_errors += 1
                            error_type = self._classify_error(line)
                            error_types[error_type] = error_types.get(error_type, 0) + 1
            except Exception as exc:
                self.logger.warning("Failed to read log file %s: %s", log_file, exc)

        most_common = max(error_types, key=error_types.get) if error_types else "N/A"

        # Generate recommendations
        recommendations = self._log_recommendations(error_types, total_errors)

        result = {
            "total_errors": total_errors,
            "error_types": error_types,
            "most_common": most_common,
            "recommendations": recommendations,
        }

        self.logger.info(
            "Log analysis complete — %d errors found, most common: %s",
            total_errors, most_common,
        )
        return result

    def _classify_error(self, line: str) -> str:
        """Classify a log line into a high-level error category."""
        line_lower = line.lower()
        if any(kw in line_lower for kw in ("timeout", "timed out")):
            return "timeout"
        if any(kw in line_lower for kw in ("connection", "connect", "refused", "unreachable")):
            return "connection"
        if any(kw in line_lower for kw in ("permission", "access denied", "forbidden")):
            return "permission"
        if any(kw in line_lower for kw in ("not found", "no such file", "missing")):
            return "file_not_found"
        if any(kw in line_lower for kw in ("json", "decode", "parse", "serializ")):
            return "parse_error"
        if any(kw in line_lower for kw in ("memory", "oom", "out of memory")):
            return "memory"
        if any(kw in line_lower for kw in ("ollama", "llm", "model", "inference")):
            return "llm_error"
        return "other"

    def _log_recommendations(self, error_types: Dict[str, int], total: int) -> List[str]:
        """Generate recommendations based on error pattern distribution."""
        recs: List[str] = []

        if total == 0:
            recs.append("No errors detected — system is operating normally.")
            return recs

        if "timeout" in error_types and error_types["timeout"] > 2:
            recs.append("Multiple timeouts detected. Consider increasing AGENT_TIMEOUT_SECONDS or checking network.")
        if "connection" in error_types:
            recs.append("Connection errors found. Verify that Ollama and any external APIs are reachable.")
        if "llm_error" in error_types:
            recs.append("LLM-related errors detected. Check Ollama status and model availability.")
        if "file_not_found" in error_types:
            recs.append("Missing file/directory errors. Run auto_fix('missing_dirs') to recreate required paths.")
        if "parse_error" in error_types:
            recs.append("JSON parse errors found. LLM responses may need stricter prompt formatting.")
        if "memory" in error_types:
            recs.append("Memory issues detected. Check system RAM and consider reducing MAX_CONCURRENT_AGENTS.")
        if total > 50:
            recs.append(f"High error count ({total}). Consider a full system review and log cleanup.")

        if not recs:
            recs.append(f"{total} errors detected. Review the error_types breakdown for targeted fixes.")

        return recs

    # ──────────────────────────────────────────────────────────────────
    # Auto-fix
    # ──────────────────────────────────────────────────────────────────

    def auto_fix(self, issue: str) -> dict:
        """Attempt to automatically fix a known issue.

        Args:
            issue: Description of the issue (matched against known fix patterns).

        Returns:
            {"fixed": bool, "action_taken": str, "details": str}
        """
        self.logger.info("auto_fix() called — issue: %s", issue)

        if not self.agent_config.get("auto_fix", True):
            return {
                "fixed": False,
                "action_taken": "none",
                "details": "auto_fix is disabled in DEBUGGER_CONFIG",
            }

        issue_lower = issue.lower()

        # Match against known fixes
        for fix_key, fix_info in _KNOWN_FIXES.items():
            if any(pattern in issue_lower for pattern in fix_info["patterns"]):
                self.logger.info("Matched known fix: %s", fix_key)
                return self._apply_fix(fix_key)

        self.logger.info("No automatic fix available for: %s", issue)
        return {
            "fixed": False,
            "action_taken": "none",
            "details": f"No automatic fix available for this issue. "
                       f"Known fixes: {', '.join(_KNOWN_FIXES.keys())}",
        }

    def _apply_fix(self, fix_key: str) -> dict:
        """Apply a specific known fix."""
        try:
            if fix_key == "temp_files":
                return self._fix_temp_files()
            elif fix_key == "ollama_restart":
                return self._fix_ollama_restart()
            elif fix_key == "missing_dirs":
                return self._fix_missing_dirs()
            else:
                return {"fixed": False, "action_taken": "none", "details": f"Unknown fix key: {fix_key}"}
        except Exception as exc:
            self.logger.error("auto_fix(%s) failed: %s", fix_key, exc)
            return {"fixed": False, "action_taken": fix_key, "details": f"Fix attempt failed: {exc}"}

    def _fix_temp_files(self) -> dict:
        """Clear temporary files from the project directory."""
        temp_patterns = ["*.tmp", "*.temp", "*~", "*.pyc"]
        removed = 0
        project_dir = config.DREAM_TEAM_DIR.parent  # streamclipper root

        for pattern in temp_patterns:
            for tmp_file in project_dir.rglob(pattern):
                try:
                    tmp_file.unlink()
                    removed += 1
                except Exception:
                    pass

        # Also clear __pycache__ dirs
        for cache_dir in project_dir.rglob("__pycache__"):
            try:
                shutil.rmtree(cache_dir)
                removed += 1
            except Exception:
                pass

        detail = f"Removed {removed} temporary files/dirs from {project_dir}"
        self.logger.info(detail)
        return {"fixed": True, "action_taken": "clear_temp_files", "details": detail}

    def _fix_ollama_restart(self) -> dict:
        """Attempt to restart the Ollama service."""
        # First check if Ollama is actually down
        try:
            resp = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
            if resp.status_code == 200:
                return {
                    "fixed": True,
                    "action_taken": "ollama_check",
                    "details": "Ollama is already running and responsive — no restart needed.",
                }
        except Exception:
            pass

        # Attempt restart (platform-aware)
        try:
            if os.name == "nt":
                subprocess.run(
                    ["powershell", "-Command", "Stop-Process -Name ollama -Force -ErrorAction SilentlyContinue"],
                    capture_output=True, timeout=10,
                )
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.run(["pkill", "-f", "ollama"], capture_output=True, timeout=10)
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )

            detail = "Ollama restart initiated. It may take a few seconds to become responsive."
            self.logger.info(detail)
            return {"fixed": True, "action_taken": "ollama_restart", "details": detail}
        except Exception as exc:
            return {"fixed": False, "action_taken": "ollama_restart", "details": f"Failed to restart Ollama: {exc}"}

    def _fix_missing_dirs(self) -> dict:
        """Recreate required project directories if they are missing."""
        required_dirs = [
            config.LOGS_DIR,
            config.AGENTS_DIR,
            config.DREAM_TEAM_DIR / "data",
            config.DREAM_TEAM_DIR / "temp",
            config.DREAM_TEAM_DIR / "exports",
        ]

        created: List[str] = []
        for d in required_dirs:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(str(d))

        if created:
            detail = f"Created {len(created)} missing directories: {', '.join(created)}"
        else:
            detail = "All required directories already exist."

        self.logger.info(detail)
        return {"fixed": True, "action_taken": "recreate_dirs", "details": detail}

    # ──────────────────────────────────────────────────────────────────
    # Log cleanup
    # ──────────────────────────────────────────────────────────────────

    def cleanup_old_logs(self, days: int = None) -> int:
        """Remove log entries older than the retention period.

        Args:
            days: Retention window in days.  Defaults to
                  ``config.DEBUGGER_CONFIG['log_retention_days']``.

        Returns:
            Number of cleaned (deleted) log files.
        """
        retention = days if days is not None else self.agent_config.get("log_retention_days", 30)
        self.logger.info("cleanup_old_logs(retention=%d days)", retention)

        cutoff = datetime.utcnow() - timedelta(days=retention)
        log_path = config.LOGS_DIR

        if not log_path.exists():
            self.logger.info("Logs directory does not exist — nothing to clean")
            return 0

        cleaned = 0
        for log_file in log_path.glob("*.log"):
            try:
                mtime = datetime.utcfromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    cleaned += 1
                    self.logger.debug("Removed old log: %s (modified %s)", log_file.name, mtime.isoformat())
            except Exception as exc:
                self.logger.warning("Failed to remove log file %s: %s", log_file, exc)

        # Also clean old error entries from shared memory
        try:
            error_entries = self.memory.search(category="errors", limit=1000)
            mem_cleaned = 0
            for entry in error_entries:
                created = entry.get("created", "")
                if created and created < cutoff.isoformat():
                    self.memory.delete(entry["key"])
                    mem_cleaned += 1
            if mem_cleaned:
                self.logger.info("Cleaned %d old error entries from shared memory", mem_cleaned)
                cleaned += mem_cleaned
        except Exception as exc:
            self.logger.warning("Failed to clean shared memory errors: %s", exc)

        self.logger.info("Log cleanup complete — %d entries removed (retention=%dd)", cleaned, retention)
        return cleaned
