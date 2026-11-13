#!/usr/bin/env bash
# Expunge only already-downloaded (\Seen) mail older than N days across all mailboxes.
# Un-downloaded (unseen) mail is never touched — POP clients don't lose mail.
set -euo pipefail
DAYS="${MAIL_RETENTION_DAYS:-30}"
doveadm expunge -A mailbox INBOX SEEN savedbefore "${DAYS}d"
