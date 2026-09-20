"use client";

import { useId } from "react";
import { useTranslations, useLocale } from "next-intl";
import type { TrendPoint } from "@/lib/stats-api";

interface Props {
  trend: TrendPoint[];
  currency: string;
}

const WIDTH = 600;
const HEIGHT = 220;
const PADDING = { top: 16, right: 12, bottom: 34, left: 52 };

function parseAmount(value: string): number {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function buildTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / 3;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const residual = rough / magnitude;
  const step =
    (residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10) * magnitude;
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= top + step / 2; value += step) {
    ticks.push(value);
  }
  return ticks;
}

export default function SpendTrendChart({ trend, currency }: Props) {
  const t = useTranslations("Dashboard");
  const locale = useLocale();
  const gradientId = useId().replace(/[^a-zA-Z0-9_-]/g, "");

  const hasData = trend.some(
    (point) => parseAmount(point.paid_total) > 0 || parseAmount(point.due_total) > 0,
  );

  const formatMonth = (period: string): string => {
    const label = new Intl.DateTimeFormat(locale, { month: "short" }).format(
      new Date(`${period}-01T00:00:00`),
    );
    return label.charAt(0).toUpperCase() + label.slice(1);
  };

  const amountFormatter = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  if (!hasData) {
    return (
      <p className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400 dark:border-slate-700 dark:text-slate-500">
        {t("trendEmpty")}
      </p>
    );
  }

  const ticks = buildTicks(
    Math.max(
      ...trend.flatMap((point) => [
        parseAmount(point.paid_total),
        parseAmount(point.due_total),
      ]),
    ),
  );
  const top = ticks[ticks.length - 1];
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const bottom = PADDING.top + plotHeight;

  const xAt = (index: number): number =>
    trend.length === 1
      ? PADDING.left + plotWidth / 2
      : PADDING.left + (plotWidth * index) / (trend.length - 1);
  const yAt = (value: number): number =>
    PADDING.top + plotHeight * (1 - value / top);

  const linePath = (key: "paid_total" | "due_total"): string =>
    `M ${trend
      .map((point, index) => `${xAt(index)},${yAt(parseAmount(point[key]))}`)
      .join(" L ")}`;

  const paidLine = linePath("paid_total");
  const paidArea = `${paidLine} L ${xAt(trend.length - 1)},${bottom} L ${xAt(0)},${bottom} Z`;
  const dueLine = linePath("due_total");

  const tickFormatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });

  return (
    <div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto"
        role="img"
        aria-label={t("trendAriaLabel")}
      >
        <defs>
          <linearGradient
            id={gradientId}
            x1="0"
            y1="0"
            x2="0"
            y2="1"
            className="text-emerald-500"
          >
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.35" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Horizontal gridlines + y-axis labels */}
        {ticks.map((tick) => (
          <g key={tick} className="text-slate-200 dark:text-slate-700">
            <line
              x1={PADDING.left}
              y1={yAt(tick)}
              x2={WIDTH - PADDING.right}
              y2={yAt(tick)}
              stroke="currentColor"
              strokeWidth={1}
            />
            <text
              x={PADDING.left - 8}
              y={yAt(tick) + 4}
              textAnchor="end"
              className="fill-slate-400 text-[11px] dark:fill-slate-500"
            >
              {tickFormatter.format(tick)}
            </text>
          </g>
        ))}

        {/* Due line (dashed) */}
        <path
          d={dueLine}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeDasharray="6 4"
          className="text-slate-400 dark:text-slate-500"
        />

        {/* Paid area + line */}
        <path d={paidArea} fill={`url(#${gradientId})`} />
        <path
          d={paidLine}
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          className="text-emerald-500"
        />

        {/* Paid dots with native tooltips */}
        {trend.map((point, index) => (
          <circle
            key={`paid-${point.period}`}
            cx={xAt(index)}
            cy={yAt(parseAmount(point.paid_total))}
            r={3.5}
            fill="currentColor"
            className="text-emerald-500"
          >
            <title>
              {`${formatMonth(point.period)} · ${t("trendPaid")}: ${amountFormatter.format(parseAmount(point.paid_total))} ${currency}`}
            </title>
          </circle>
        ))}

        {/* Due dots with native tooltips */}
        {trend.map((point, index) => (
          <circle
            key={`due-${point.period}`}
            cx={xAt(index)}
            cy={yAt(parseAmount(point.due_total))}
            r={2.5}
            fill="currentColor"
            className="text-slate-400 dark:text-slate-500"
          >
            <title>
              {`${formatMonth(point.period)} · ${t("trendDue")}: ${amountFormatter.format(parseAmount(point.due_total))} ${currency}`}
            </title>
          </circle>
        ))}

        {/* X-axis month labels */}
        {trend.map((point, index) => (
          <text
            key={`label-${point.period}`}
            x={xAt(index)}
            y={HEIGHT - 10}
            textAnchor="middle"
            className="fill-slate-400 text-[11px] dark:fill-slate-500"
          >
            {formatMonth(point.period)}
          </text>
        ))}
      </svg>

      <div className="mt-1 flex items-center gap-5 text-xs text-slate-500 dark:text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          {t("trendPaid")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0 w-4 border-t-2 border-dashed border-slate-400 dark:border-slate-500" />
          {t("trendDue")}
        </span>
      </div>
    </div>
  );
}
