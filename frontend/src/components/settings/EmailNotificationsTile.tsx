"use client";

import { AlertTriangle, BarChart2, Loader2, Mail, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  fetchNotificationStatus,
  fetchServerTime,
  sendMonthlySummaryNow,
  sendNotificationNow,
  sendTestNotification,
  updateMe,
  type NotificationStatus,
  type TestNotificationResult,
  type UserProfile,
} from "@/lib/user-api";
import { Switch } from "@/components/ui/Switch";
import { Tile } from "./Tile";

const SLOTS = Array.from({ length: 48 }, (_, i) => i * 30);
function fmtSlot(minutes: number) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function EmailNotificationsTile({
  profile,
  onProfileUpdate,
  onDirtyChange,
  t,
  isCollapsed,
  onToggle,
}: {
  profile: UserProfile;
  onProfileUpdate: (p: UserProfile) => void;
  onDirtyChange: (dirty: boolean) => void;
  t: ReturnType<typeof useTranslations>;
  isCollapsed?: boolean;
  onToggle?: () => void;
}) {
  const tp = useTranslations("SettingsPage");

  const [emailEnabled, setEmailEnabled] = useState(profile.email_reminders_enabled);
  const [notify2, setNotify2] = useState(profile.notify_2_days_before);
  const [notify1, setNotify1] = useState(profile.notify_1_day_before);
  const [notifyOn, setNotifyOn] = useState(profile.notify_on_day);
  const [notify1After, setNotify1After] = useState(profile.notify_1_day_after);
  const [sendMinute, setSendMinute] = useState(profile.reminder_send_minute);
  const [monthlySummary, setMonthlySummary] = useState(profile.monthly_summary_enabled);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isTogglingEnabled, setIsTogglingEnabled] = useState(false);
  const [isTogglingMonthlySummary, setIsTogglingMonthlySummary] = useState(false);
  const [isSendingNow, setIsSendingNow] = useState(false);
  const [sendNowResult, setSendNowResult] = useState<
    { sent: number } | { error: string } | null
  >(null);
  const [isSendingSummary, setIsSendingSummary] = useState(false);
  const [sendSummaryResult, setSendSummaryResult] = useState<
    { sent: boolean } | { error: string } | null
  >(null);
  const [notificationStatus, setNotificationStatus] =
    useState<NotificationStatus | null>(null);
  const [isSendingTest, setIsSendingTest] = useState(false);
  const [testResult, setTestResult] =
    useState<TestNotificationResult | { error: string } | null>(null);
  const [serverTime, setServerTime] = useState<string | null>(null);

  useEffect(() => {
    fetchNotificationStatus()
      .then(setNotificationStatus)
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchServerTime()
      .then(({ server_time }) => {
        const formatted = new Intl.DateTimeFormat("en-GB", {
          year: "numeric",
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "UTC",
          timeZoneName: "short",
        }).format(new Date(server_time));
        setServerTime(formatted);
      })
      .catch(() => {});
  }, []);

  const isDirty =
    notify2 !== profile.notify_2_days_before ||
    notify1 !== profile.notify_1_day_before ||
    notifyOn !== profile.notify_on_day ||
    notify1After !== profile.notify_1_day_after ||
    sendMinute !== profile.reminder_send_minute;

  const noneSelected = !notify2 && !notify1 && !notifyOn && !notify1After;
  const smtpConfigured = notificationStatus?.smtp_configured ?? false;
  const appriseConfigured = notificationStatus?.apprise_configured ?? false;
  const noChannelConfigured =
    notificationStatus !== null && !smtpConfigured && !appriseConfigured;

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  async function handleEmailEnabledChange(value: boolean) {
    setEmailEnabled(value);
    setIsTogglingEnabled(true);
    try {
      const updated = await updateMe({ email_reminders_enabled: value });
      onProfileUpdate(updated);
    } catch {
      // Revert on failure
      setEmailEnabled(!value);
    } finally {
      setIsTogglingEnabled(false);
    }
  }

  function cancel() {
    setNotify2(profile.notify_2_days_before);
    setNotify1(profile.notify_1_day_before);
    setNotifyOn(profile.notify_on_day);
    setNotify1After(profile.notify_1_day_after);
    setSendMinute(profile.reminder_send_minute);
    setSaveError(null);
  }

  async function handleMonthlySummaryChange(value: boolean) {
    setMonthlySummary(value);
    setIsTogglingMonthlySummary(true);
    try {
      const updated = await updateMe({ monthly_summary_enabled: value });
      onProfileUpdate(updated);
    } catch {
      setMonthlySummary(!value);
    } finally {
      setIsTogglingMonthlySummary(false);
    }
  }

  async function save() {
    setIsSaving(true);
    setSaveError(null);
    try {
      const updated = await updateMe({
        notify_2_days_before: notify2,
        notify_1_day_before: notify1,
        notify_on_day: notifyOn,
        notify_1_day_after: notify1After,
        reminder_send_minute: sendMinute,
      });
      onProfileUpdate(updated);
    } catch {
      setSaveError(tp("saveFailed"));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSendNow() {
    setIsSendingNow(true);
    setSendNowResult(null);
    try {
      const result = await sendNotificationNow();
      setSendNowResult(result);
    } catch (err) {
      setSendNowResult({ error: err instanceof Error ? err.message : tp("saveFailed") });
    } finally {
      setIsSendingNow(false);
    }
  }

  async function handleSendSummary() {
    setIsSendingSummary(true);
    setSendSummaryResult(null);
    try {
      const result = await sendMonthlySummaryNow();
      setSendSummaryResult(result);
    } catch (err) {
      setSendSummaryResult({ error: err instanceof Error ? err.message : tp("saveFailed") });
    } finally {
      setIsSendingSummary(false);
    }
  }

  async function handleSendTest() {
    setIsSendingTest(true);
    setTestResult(null);
    try {
      const result = await sendTestNotification();
      setTestResult(result);
    } catch (err) {
      setTestResult({ error: err instanceof Error ? err.message : tp("saveFailed") });
    } finally {
      setIsSendingTest(false);
    }
  }

  const checkboxClass =
    "h-4 w-4 rounded border-slate-200 accent-green-700 focus:ring-green-500 dark:border-slate-600";
  const labelClass = "ml-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer";

  const checkboxes: [string, boolean, (v: boolean) => void, string][] = [
    ["2-before", notify2, setNotify2, tp("emailNotifications.twoDaysBefore")],
    ["1-before", notify1, setNotify1, tp("emailNotifications.oneDayBefore")],
    ["on-day", notifyOn, setNotifyOn, tp("emailNotifications.onDay")],
    ["1-after", notify1After, setNotify1After, tp("emailNotifications.oneDayAfter")],
  ];

  return (
    <Tile
      color="yellow"
      icon={Mail}
      title={tp("emailNotifications.title")}
      description={tp("emailNotifications.description")}
      t={t}
      isCollapsed={isCollapsed}
      onToggle={onToggle}
    >
      <Switch
        checked={emailEnabled}
        onChange={handleEmailEnabledChange}
        label={tp("emailNotifications.masterToggle")}
        disabled={isTogglingEnabled}
      />

      <div className={!emailEnabled ? "opacity-50 pointer-events-none" : ""}>
        <div className="space-y-2">
          {checkboxes.map(([key, checked, setter, label]) => (
            <label key={key} className="flex items-center">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => setter(e.target.checked)}
                className={checkboxClass}
              />
              <span className={labelClass}>{label}</span>
            </label>
          ))}
        </div>

        {noneSelected && (
          <div className="flex items-start gap-2 rounded-lg bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-700 px-3 py-2 mt-2">
            <AlertTriangle size={15} className="text-yellow-600 dark:text-yellow-400 mt-0.5 shrink-0" />
            <p className="text-sm text-yellow-700 dark:text-yellow-300">
              {tp("emailNotifications.noneWarning")}
            </p>
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300 whitespace-nowrap">
            {tp("emailNotifications.sendTimeLabel")}
          </label>
          <select
            value={sendMinute}
            onChange={(e) => setSendMinute(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm outline-none transition-all hover:border-slate-300 focus:border-green-500 focus:ring-2 focus:ring-green-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-500 dark:focus:border-green-600 dark:focus:ring-green-900/40"
          >
            {SLOTS.map((h) => (
              <option key={h} value={h}>{fmtSlot(h)}</option>
            ))}
          </select>
        </div>

        {isDirty && (
          <div className="flex flex-col gap-1 pt-1">
            <div className="flex gap-2">
              <button
                onClick={save}
                disabled={isSaving}
                className="rounded-lg border border-green-700 bg-green-700 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:border-green-800 hover:bg-green-800 disabled:opacity-50"
              >
                {isSaving ? t("saving") : t("save")}
              </button>
              <button
                onClick={cancel}
                disabled={isSaving}
                className="rounded-lg border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {t("cancel")}
              </button>
            </div>
            {saveError && (
              <p className="text-sm text-red-600 dark:text-red-400">{saveError}</p>
            )}
          </div>
        )}

        <div className="flex flex-col gap-2 pt-1 border-t border-slate-100 dark:border-slate-700">
          <button
            onClick={handleSendNow}
            disabled={isSendingNow || !emailEnabled || isDirty || noChannelConfigured}
            className="flex items-center gap-2 self-start rounded-lg border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-green-300 hover:bg-green-50 hover:text-green-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-emerald-700 dark:hover:bg-emerald-900/20 dark:hover:text-emerald-400"
          >
            {isSendingNow ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {isSendingNow ? tp("emailNotifications.sendNowSending") : tp("emailNotifications.sendNowButton")}
          </button>

          {sendNowResult && "error" in sendNowResult && (
            <p className="text-sm text-red-600 dark:text-red-400">{sendNowResult.error}</p>
          )}
          {sendNowResult && "sent" in sendNowResult && (
            <p className="text-sm text-green-600 dark:text-green-500">
              {sendNowResult.sent === 0
                ? tp("emailNotifications.sendNowNoReminders")
                : tp("emailNotifications.sendNowSent", { count: sendNowResult.sent })}
            </p>
          )}

          <div className="pt-1 border-t border-slate-100 dark:border-slate-700">
            <Switch
              checked={monthlySummary}
              onChange={handleMonthlySummaryChange}
              label={tp("emailNotifications.monthlySummaryToggle")}
              disabled={isTogglingMonthlySummary}
            />
          </div>

          <button
            onClick={handleSendSummary}
            disabled={isSendingSummary || !emailEnabled || !monthlySummary || isDirty || noChannelConfigured}
            className="flex items-center gap-2 self-start rounded-lg border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-green-300 hover:bg-green-50 hover:text-green-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-emerald-700 dark:hover:bg-emerald-900/20 dark:hover:text-emerald-400"
          >
            {isSendingSummary ? <Loader2 size={14} className="animate-spin" /> : <BarChart2 size={14} />}
            {isSendingSummary
              ? tp("emailNotifications.sendMonthlySummarySending")
              : tp("emailNotifications.sendMonthlySummaryButton")}
          </button>

          {sendSummaryResult && "error" in sendSummaryResult && (
            <p className="text-sm text-red-600 dark:text-red-400">{sendSummaryResult.error}</p>
          )}
          {sendSummaryResult && "sent" in sendSummaryResult && (
            <p className="text-sm text-green-600 dark:text-green-500">
              {sendSummaryResult.sent
                ? tp("emailNotifications.sendMonthlySummarySent")
                : tp("emailNotifications.sendMonthlySummaryNoData")}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-2 pt-1 border-t border-slate-100 dark:border-slate-700">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {tp("emailNotifications.channelsLabel")}
        </p>

        <div className="flex items-center justify-between gap-2">
          <span className="text-sm text-slate-600 dark:text-slate-400">
            {tp("emailNotifications.smtpChannel")}
          </span>
          <span
            className={
              smtpConfigured
                ? "text-sm text-green-600 dark:text-green-500"
                : "text-sm text-slate-400 dark:text-slate-500"
            }
          >
            {smtpConfigured
              ? tp("emailNotifications.channelConfigured")
              : tp("emailNotifications.channelNotConfigured")}
          </span>
        </div>

        <div className="flex items-center justify-between gap-2">
          <span className="text-sm text-slate-600 dark:text-slate-400">
            {tp("emailNotifications.appriseChannel")}
          </span>
          <span
            className={
              appriseConfigured
                ? "text-sm text-green-600 dark:text-green-500"
                : "text-sm text-slate-400 dark:text-slate-500"
            }
          >
            {appriseConfigured
              ? tp("emailNotifications.channelConfigured")
              : tp("emailNotifications.channelNotConfigured")}
          </span>
        </div>

        {noChannelConfigured && (
          <div className="flex items-start gap-2 rounded-lg bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-700 px-3 py-2">
            <AlertTriangle size={15} className="text-yellow-600 dark:text-yellow-400 mt-0.5 shrink-0" />
            <p className="text-sm text-yellow-700 dark:text-yellow-300">
              {tp("emailNotifications.noChannelWarning")}
            </p>
          </div>
        )}

        <button
          onClick={handleSendTest}
          disabled={isSendingTest}
          className="flex items-center gap-2 self-start rounded-lg border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-green-300 hover:bg-green-50 hover:text-green-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-emerald-700 dark:hover:bg-emerald-900/20 dark:hover:text-emerald-400"
        >
          {isSendingTest ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          {isSendingTest
            ? tp("emailNotifications.sendTestSending")
            : tp("emailNotifications.sendTestButton")}
        </button>

        {testResult && "error" in testResult && (
          <p className="text-sm text-red-600 dark:text-red-400">{testResult.error}</p>
        )}
        {testResult && "ok" in testResult && (
          <p
            className={
              testResult.ok
                ? "text-sm text-green-600 dark:text-green-500"
                : "text-sm text-red-600 dark:text-red-400"
            }
          >
            {testResult.ok
              ? testResult.channel === "apprise"
                ? tp("emailNotifications.testSentViaApprise")
                : tp("emailNotifications.testSentViaEmail")
              : (testResult.detail ?? tp("emailNotifications.testFailed"))}
          </p>
        )}
      </div>

      {serverTime && (
        <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
          {tp("emailNotifications.serverTimeHint", { time: serverTime })}
        </p>
      )}
    </Tile>
  );
}
