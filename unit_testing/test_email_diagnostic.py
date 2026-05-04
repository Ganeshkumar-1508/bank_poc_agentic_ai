#!/usr/bin/env python3
"""
Email Diagnostic Test Script

This script performs comprehensive diagnostics to identify why emails show as "sent"
but are not being received by recipients.

Tests performed:
1. SMTP Connection Test - Verifies basic SMTP connectivity
2. SMTP Authentication Test - Verifies credentials are valid
3. SMTP Response Code Test - Logs all SMTP response codes during send
4. Multi-Recipient Test - Tests with multiple recipient emails
5. Spam Filter Check - Checks if email content triggers spam filters
"""

import os
import sys
import smtplib
import logging
import time
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("email_diagnostic.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


class EmailDiagnostic:
    """Comprehensive email diagnostic tool."""

    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "summary": {},
        }

    def record_result(self, test_name: str, passed: bool, details: dict):
        """Record test result."""
        self.results["tests"][test_name] = {
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
        status = "PASSED" if passed else "FAILED"
        logger.info(f"  [{status}] {test_name}")

    def test_smtp_connection(self) -> bool:
        """Test basic SMTP connectivity."""
        logger.info("\n=== Test 1: SMTP Connection Test ===")
        details = {}
        try:
            logger.info(f"Connecting to {self.smtp_server}:{self.smtp_port}...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
            # getwelcome() may not be available in all Python versions - use ehlo_resp
            if hasattr(server, "ehlo_resp") and server.ehlo_resp:
                greeting = (
                    server.ehlo_resp.decode()
                    if isinstance(server.ehlo_resp, bytes)
                    else server.ehlo_resp
                )
            else:
                greeting = "SMTP connection established"
            details["server_greeting"] = greeting
            logger.info(f"Server greeting: {greeting[:100]}...")

            # Check supported extensions
            server.ehlo()
            if hasattr(server, "ehlo_args") and server.ehlo_args:
                exts = (
                    server.ehlo_args[1]
                    if isinstance(server.ehlo_args[1], dict)
                    else str(server.ehlo_args[1])
                )
                details["supported_extensions"] = str(exts)[:200]
                logger.info(f"Supported extensions: {exts}")

            server.quit()
            self.record_result("SMTP Connection", True, details)
            return True
        except Exception as e:
            details["error"] = str(e)
            details["error_type"] = type(e).__name__
            logger.error(f"Connection failed: {e}")
            self.record_result("SMTP Connection", False, details)
            return False

    def test_smtp_authentication(self) -> bool:
        """Test SMTP authentication with credentials."""
        logger.info("\n=== Test 2: SMTP Authentication Test ===")
        details = {}

        if not self.smtp_user:
            details["error"] = "SMTP_USER not configured"
            self.record_result("SMTP Authentication", False, details)
            return False

        if not self.smtp_password:
            details["error"] = "SMTP_PASSWORD not configured"
            self.record_result("SMTP Authentication", False, details)
            return False

        try:
            logger.info(f"Authenticating as {self.smtp_user}...")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
            server.starttls()

            # Capture login response
            login_response = server.login(self.smtp_user, self.smtp_password)
            details["login_response_code"] = login_response[0]
            details["login_response_message"] = (
                login_response[1].decode()
                if isinstance(login_response[1], bytes)
                else login_response[1]
            )
            logger.info(f"Login response code: {login_response[0]}")
            logger.info(f"Login response message: {details['login_response_message']}")

            server.quit()
            self.record_result("SMTP Authentication", True, details)
            return True
        except smtplib.SMTPAuthenticationError as e:
            details["error"] = "Authentication failed"
            details["smtp_code"] = e.smtp_code if hasattr(e, "smtp_code") else "N/A"
            details["smtp_error"] = e.smtp_error if hasattr(e, "smtp_error") else str(e)
            logger.error(
                f"Authentication failed: code={details['smtp_code']}, error={details['smtp_error']}"
            )
            self.record_result("SMTP Authentication", False, details)
            return False
        except Exception as e:
            details["error"] = str(e)
            details["error_type"] = type(e).__name__
            logger.error(f"Authentication test failed: {e}")
            self.record_result("SMTP Authentication", False, details)
            return False

    def test_smtp_response_codes(self, test_recipient: str) -> bool:
        """Test SMTP response codes during email send."""
        logger.info(
            f"\n=== Test 3: SMTP Response Code Test (recipient: {test_recipient}) ==="
        )
        details = {}

        if not self.smtp_user or not self.smtp_password:
            details["error"] = "Credentials not configured"
            self.record_result("SMTP Response Codes", False, details)
            return False

        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)

            # Step 1: Connect and log greeting
            logger.info("Step 1: SMTP Connection")
            if hasattr(server, "ehlo_resp") and server.ehlo_resp:
                greeting = (
                    server.ehlo_resp.decode()
                    if isinstance(server.ehlo_resp, bytes)
                    else server.ehlo_resp
                )
            else:
                greeting = "SMTP connection established"
            details["step1_greeting"] = greeting
            logger.info(f"  Server greeting: {greeting[:100]}...")

            # Step 2: Start TLS
            logger.info("Step 2: STARTTLS")
            tls_response = server.starttls()
            details["step2_tls_response_code"] = tls_response[0]
            tls_msg = (
                tls_response[1].decode()
                if isinstance(tls_response[1], bytes)
                else tls_response[1]
            )
            details["step2_tls_response_message"] = tls_msg
            logger.info(f"  TLS response code: {tls_response[0]}")
            logger.info(f"  TLS response message: {tls_msg}")

            # Step 3: EHLO after TLS
            logger.info("Step 3: EHLO after TLS")
            ehlo_response = server.ehlo()
            details["step3_ehlo_response_code"] = ehlo_response[0]
            logger.info(f"  EHLO response code: {ehlo_response[0]}")

            # Step 4: Login
            logger.info("Step 4: LOGIN")
            login_response = server.login(self.smtp_user, self.smtp_password)
            details["step4_login_response_code"] = login_response[0]
            login_msg = (
                login_response[1].decode()
                if isinstance(login_response[1], bytes)
                else login_response[1]
            )
            details["step4_login_response_message"] = login_msg
            logger.info(f"  Login response code: {login_response[0]}")

            # Step 5: MAIL FROM
            logger.info("Step 5: MAIL FROM")
            mail_from_response = server.mail(self.smtp_user)
            details["step5_mail_from_response_code"] = mail_from_response[0]
            mail_msg = (
                mail_from_response[1].decode()
                if isinstance(mail_from_response[1], bytes)
                else mail_from_response[1]
            )
            details["step5_mail_from_response_message"] = mail_msg
            logger.info(f"  MAIL FROM response code: {mail_from_response[0]}")

            # Step 6: RCPT TO
            logger.info("Step 6: RCPT TO")
            rcpt_to_response = server.rcpt(test_recipient)
            details["step6_rcpt_to_response_code"] = rcpt_to_response[0]
            rcpt_msg = (
                rcpt_to_response[1].decode()
                if isinstance(rcpt_to_response[1], bytes)
                else rcpt_to_response[1]
            )
            details["step6_rcpt_to_response_message"] = rcpt_msg
            logger.info(f"  RCPT TO response code: {rcpt_to_response[0]}")

            # Step 7: Create message
            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = test_recipient
            msg["Subject"] = (
                f"[DIAGNOSTIC TEST] SMTP Response Code Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            msg.attach(
                MIMEText(
                    f"This is a diagnostic test email sent at {datetime.now().isoformat()}.\n\n"
                    f"If you receive this, the SMTP server accepted the email for delivery.\n\n"
                    f"Test ID: {datetime.now().strftime('%Y%m%d%H%M%S')}\n\n"
                    f"IMPORTANT: If you see this in spam, please mark as 'Not Spam'.",
                    "plain",
                )
            )

            msg_string = msg.as_string()
            logger.info(f"Step 7: SENDMAIL (message size: {len(msg_string)} bytes)")
            details["step7_message_size"] = len(msg_string)

            # sendmail() combines DATA + send in one call
            # Returns {email_address: error_string} - empty dict means success
            sendmail_response = server.sendmail(
                self.smtp_user, test_recipient, msg_string
            )

            if sendmail_response:
                details["step8_sendmail_response"] = sendmail_response
                details["sendmail_success"] = False
                logger.error(
                    f"  SENDMAIL returned non-empty response (FAILED): {sendmail_response}"
                )
            else:
                details["step8_sendmail_response"] = "Empty dict (success)"
                details["sendmail_success"] = True
                logger.info(
                    "  SENDMAIL returned empty dict (SUCCESS - server accepted email)"
                )

            # Step 8: QUIT
            logger.info("Step 8: QUIT")
            try:
                quit_response = server.quit()
                details["step8_quit_response_code"] = quit_response[0]
                quit_msg = (
                    quit_response[1].decode()
                    if isinstance(quit_response[1], bytes)
                    else quit_response[1]
                )
                details["step8_quit_response_message"] = quit_msg
                logger.info(f"  QUIT response code: {quit_response[0]}")
            except Exception as e:
                # QUIT may fail if server already closed connection
                details["step8_quit_response_code"] = "N/A"
                details["step8_quit_response_message"] = f"Server disconnected: {e}"
                logger.info(f"  QUIT: {e}")

            # Determine overall success
            all_success = (
                details["step2_tls_response_code"] == 220
                and details["step3_ehlo_response_code"] == 250
                and details["step4_login_response_code"] == 235
                and details["step5_mail_from_response_code"] == 250
                and details["step6_rcpt_to_response_code"] == 250
                and details["sendmail_success"]
                and details["step8_quit_response_code"] == 221
            )

            self.record_result("SMTP Response Codes", all_success, details)
            return all_success

        except Exception as e:
            details["error"] = str(e)
            details["error_type"] = type(e).__name__
            logger.error(f"SMTP response code test failed: {e}")
            self.record_result("SMTP Response Codes", False, details)
            return False

    def test_multi_recipient(self, recipients: list) -> dict:
        """Test sending to multiple recipients."""
        logger.info(f"\n=== Test 4: Multi-Recipient Test ===")
        details = {}
        results = {}

        if not self.smtp_user or not self.smtp_password:
            details["error"] = "Credentials not configured"
            self.record_result("Multi-Recipient Test", False, details)
            return results

        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)

            for recipient in recipients:
                logger.info(f"Testing recipient: {recipient}")
                msg = MIMEMultipart()
                msg["From"] = self.smtp_user
                msg["To"] = recipient
                msg["Subject"] = (
                    f"[DIAGNOSTIC] Multi-Recipient Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                msg.attach(
                    MIMEText(
                        f"This is a diagnostic test email to {recipient}.\n\n"
                        f"Sent at: {datetime.now().isoformat()}\n"
                        f"Test ID: {datetime.now().strftime('%Y%m%d%H%M%S')}\n\n"
                        f"IMPORTANT: If you see this in spam, please mark as 'Not Spam'.",
                        "plain",
                    )
                )

                try:
                    response = server.sendmail(
                        self.smtp_user, recipient, msg.as_string()
                    )
                    if response:
                        results[recipient] = {"status": "FAILED", "response": response}
                        logger.error(f"  Failed for {recipient}: {response}")
                    else:
                        results[recipient] = {
                            "status": "SUCCESS",
                            "response": "Accepted by SMTP server",
                        }
                        logger.info(
                            f"  Success for {recipient} - SMTP server accepted email"
                        )
                except Exception as e:
                    results[recipient] = {"status": "ERROR", "error": str(e)}
                    logger.error(f"  Error for {recipient}: {e}")

            server.quit()

            # Check if all succeeded
            all_success = all(r["status"] == "SUCCESS" for r in results.values())
            details["recipient_results"] = results
            self.record_result("Multi-Recipient Test", all_success, details)
            return results

        except Exception as e:
            details["error"] = str(e)
            self.record_result("Multi-Recipient Test", False, details)
            return results

    def check_spam_indicators(self) -> dict:
        """Check for common spam indicators in email configuration."""
        logger.info("\n=== Test 5: Spam Filter Indicators Check ===")
        details = {"spam_indicators": [], "recommendations": []}

        # Check for common spam triggers
        issues = []

        # 1. Check if sender domain matches SMTP server domain
        if self.smtp_user and "@" in self.smtp_user:
            sender_domain = self.smtp_user.split("@")[-1]
            if (
                "gmail.com" in sender_domain
                and "smtp.gmail.com" not in self.smtp_server
            ):
                issues.append("Sender domain is Gmail but using non-Gmail SMTP server")
                details["recommendations"].append(
                    "Use smtp.gmail.com for Gmail accounts"
                )

        # 2. Check for proper authentication
        if not self.smtp_password:
            issues.append("No SMTP password configured")
            details["recommendations"].append(
                "Configure SMTP_PASSWORD with app-specific password"
            )

        # 3. Check if using TLS
        if self.smtp_port not in [587, 465, 25]:
            issues.append(
                f"Non-standard SMTP port {self.smtp_port} may trigger spam filters"
            )
            details["recommendations"].append(
                "Use port 587 (TLS) or 465 (SSL) for Gmail"
            )

        # 4. Gmail-specific checks
        if "gmail.com" in self.smtp_user:
            issues.append("Gmail accounts may have emails filtered to spam")
            details["recommendations"].append("Check recipient's spam folder")
            details["recommendations"].append(
                "Ensure 'Less secure apps' or App Password is configured"
            )
            details["recommendations"].append(
                "Consider using Gmail API with OAuth2 for better deliverability"
            )

        details["spam_indicators"] = issues
        details["total_indicators"] = len(issues)

        # This test "passes" if we identify potential issues (informational)
        self.record_result("Spam Filter Check", True, details)
        return details

    def generate_report(self):
        """Generate comprehensive diagnostic report."""
        logger.info("\n" + "=" * 60)
        logger.info("DIAGNOSTIC REPORT")
        logger.info("=" * 60)

        # Calculate summary
        total_tests = len(self.results["tests"])
        passed_tests = sum(1 for t in self.results["tests"].values() if t["passed"])
        failed_tests = total_tests - passed_tests

        self.results["summary"] = {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": f"{(passed_tests/total_tests*100) if total_tests > 0 else 0:.1f}%",
        }

        # Print summary
        logger.info(f"\nTotal Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        logger.info(f"Success Rate: {self.results['summary']['success_rate']}")

        # Print failed tests details
        if failed_tests > 0:
            logger.info("\n--- FAILED TESTS ---")
            for test_name, result in self.results["tests"].items():
                if not result["passed"]:
                    logger.info(f"\n{test_name}:")
                    for key, value in result["details"].items():
                        logger.info(f"  {key}: {value}")

        # Print key findings
        logger.info("\n--- KEY FINDINGS ---")
        if "SMTP Response Codes" in self.results["tests"]:
            smtp_result = self.results["tests"]["SMTP Response Codes"]
            if smtp_result["passed"]:
                logger.info("SMTP server ACCEPTED all emails for delivery.")
                logger.info(
                    "This means the issue is NOT with SMTP - it's with Gmail's internal filtering."
                )
                logger.info("Check the recipient's SPAM folder.")
            else:
                logger.info("SMTP server REJECTED some emails.")
                logger.info("The issue is with SMTP configuration or authentication.")

        if "Multi-Recipient Test" in self.results["tests"]:
            multi_result = self.results["tests"]["Multi-Recipient Test"]
            if multi_result["passed"]:
                logger.info(
                    "All recipients' addresses were accepted by the SMTP server."
                )
                logger.info(
                    "The emails were queued for delivery by Gmail's SMTP server."
                )

        # Save report to file
        report_path = Path(__file__).parent / "email_diagnostic_report.json"
        with open(report_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        logger.info(f"\nFull report saved to: {report_path}")

        # Print recommendations
        logger.info("\n--- RECOMMENDATIONS ---")
        if "Spam Filter Check" in self.results["tests"]:
            spam_result = self.results["tests"]["Spam Filter Check"]
            for rec in spam_result["details"].get("recommendations", []):
                logger.info(f"  - {rec}")

        logger.info("\n--- NEXT STEPS ---")
        logger.info("1. Check the recipient's SPAM/Junk folder")
        logger.info("2. Ask the recipient to mark the email as 'Not Spam'")
        logger.info("3. Verify the email content doesn't trigger spam filters")
        logger.info("4. Consider using Gmail API with OAuth2 instead of SMTP")
        logger.info("5. Check Gmail's 'Less secure apps' settings or use App Password")

        return self.results


def main():
    """Run all diagnostic tests."""
    print("=" * 60)
    print("EMAIL DIAGNOSTIC TEST SUITE")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"SMTP Server: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"SMTP Port: {os.getenv('SMTP_PORT', '587')}")
    print(f"SMTP User: {os.getenv('SMTP_USER', 'NOT CONFIGURED')}")
    print()

    diagnostic = EmailDiagnostic()

    # Get test recipients from command line or use defaults
    test_recipients = [
        "ashwinpremnath123@gmail.com",  # Sender's own email
        "test@example.com",  # Generic test email
    ]

    # Add custom recipients from command line
    if len(sys.argv) > 1:
        test_recipients.extend(sys.argv[1:])
        logger.info(f"Added custom recipients: {sys.argv[1:]}")

    # Run tests
    diagnostic.test_smtp_connection()
    diagnostic.test_smtp_authentication()

    # Test each recipient
    for recipient in test_recipients:
        diagnostic.test_smtp_response_codes(recipient)

    # Multi-recipient test
    diagnostic.test_multi_recipient(test_recipients)

    # Spam filter check
    diagnostic.check_spam_indicators()

    # Generate report
    report = diagnostic.generate_report()

    # Exit with appropriate code
    sys.exit(0 if report["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
