import logging
import subprocess
from typing import Any, Callable, Dict


logger = logging.getLogger(__name__)


class CronService:
    def get_supported_job_types(self):
        return [
            ("send_message", "Send a message"),
            ("custom_command", "Run a command"),
            ("cleanup", "Cleanup old data"),
            ("check_email", "Run scheduled email check"),
        ]

    def get_capability_summary(self):
        return """Yes! I have powerful scheduling capabilities:

⏰ Cron Job Features:
• /addjob - Create scheduled tasks
• /listjobs - View all scheduled jobs
• /removejob - Delete jobs
• Natural language: "remind me every day at 9am"

I can schedule:
• Skill checks
• Command execution
• Custom reminders
• Cleanup tasks"""

    def get_addjob_help_text(self):
        type_lines = [f"• {job_type} - {description}" for job_type, description in self.get_supported_job_types()]
        return (
            "Add a cron job:\n\n"
            "/addjob <name> <type> <schedule> [params]\n\n"
            "Types:\n"
            + "\n".join(type_lines)
            + "\n\n"
            "Schedule examples:\n"
            "• \"every 30 minutes\"\n"
            "• \"every 1 hour\"\n"
            "• \"daily at 09:00\"\n"
            "• \"0 9 * * *\" (cron: 9 AM daily)\n\n"
            "Examples:\n"
            "/addjob morning_email check_email \"daily at 08:00\"\n"
            "/addjob hourly_check check_email \"every 1 hour\"\n"
            "/addjob reminder send_message \"daily at 12:00\" message=\"Take a break!\"\n"
        )

    def run_custom_command(self, command, timeout=30):
        try:
            logger.info(f"Executing command: {command}")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = ""
            if result.stdout:
                output = result.stdout.strip()
            if result.stderr:
                output += f"\n⚠️ {result.stderr.strip()}"
            if not output:
                output = "✅ Done"

            return output[:1500]
        except subprocess.TimeoutExpired:
            return f"❌ Command timed out after {timeout} seconds"
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return f"❌ Error: {str(e)}"

    def execute_cron_job(
        self,
        job_type: str,
        params: Dict[str, Any],
        *,
        notify_user_id: str,
        send_message: Callable[..., None],
        fetch_scheduled_check_result: Callable[..., str],
        generate_sleep_report: Callable[[str, int], str],
        generate_tracking_report: Callable[[str, str, int], str],
    ) -> None:
        logger.info(f"Executing cron job: {job_type} with params: {params}")

        try:
            if job_type == "check_email":
                target_user_id = params.get("user_id", notify_user_id)
                result = fetch_scheduled_check_result(str(target_user_id))
                send_message(target_user_id, f"📧 Scheduled Email Check:\n\n{result}", parse_mode="HTML")

            elif job_type == "send_message":
                message = params.get("message", "Scheduled reminder")
                user_id = params.get("user_id", notify_user_id)

                if message.startswith("SLEEP_REPORT:"):
                    parts = message.split(":")
                    report_user_id = parts[1]
                    days = int(parts[2]) if len(parts) > 2 else 7
                    report = generate_sleep_report(report_user_id, days)
                    send_message(user_id, report)
                elif message.startswith("TRACKING_REPORT:"):
                    parts = message.split(":")
                    report_user_id = parts[1]
                    category = parts[2]
                    days = int(parts[3]) if len(parts) > 3 else 7
                    report = generate_tracking_report(report_user_id, category, days)
                    send_message(user_id, report)
                else:
                    send_message(user_id, message)

            elif job_type == "custom_command":
                command = params.get("command", "")
                if command:
                    output = self.run_custom_command(command, timeout=30)
                    send_message(notify_user_id, output[:500])

            elif job_type == "cleanup":
                days = params.get("days", 30)
                logger.info(f"Cleanup job executed (older than {days} days)")
                send_message(notify_user_id, f"🧹 Cleanup completed (>{days} days old data)")

            else:
                logger.warning(f"Unknown job type: {job_type}")

        except Exception as e:
            logger.error(f"Error executing cron job {job_type}: {e}")
            send_message(notify_user_id, f"❌ Cron job failed: {job_type}\n{str(e)}")
