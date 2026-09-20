"use client";

import { useId } from "react";
import { useTranslations, useLocale } from "next-intl";
import type { ForecastPoint, TrendPoint } from "@/lib/stats-api";

interface Props {
  trend: TrendPoint[];
  forecast: ForecastPoint[];
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

export default function SpendTrendChart({ trend, forecast, currency }: Props) {
  const t = useTranslations("Dashboard");
  const locale = useLocale();
  const gradientId = useId().replace(/[^a-zA-Z0-9_-]/g, "");

  const hasActuals = trend.some(
    (point) => parseAmount(point.paid_total) > 0 || parseAmount(point.due_total) > 0,
  );
  const hasForecast = forecast.some(
    (point) => parseAmount(point.expected_total) > 0,
  );
  const hasData = hasActuals || hasForecast;

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

  const actualCount = trend.length;
  const totalCount = actualCount + forecast.length;
  const values = [
    ...trend.flatMap((point) => [
      parseAmount(point.paid_total),
      parseAmount(point.due_total),
    ]),
    ...forecast.map((point) => parseAmount(point.expected_total)),
  ];

  const ticks = buildTicks(values.length > 0 ? Math.max(...values) : 0);
  const top = ticks[ticks.length - 1];
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const bottom = PADDING.top + plotHeight;

  const xAt = (index: number): number =>
    totalCount <= 1
      ? PADDING.left + plotWidth / 2
      : PADDING.left + (plotWidth * index) / (totalCount - 1);
  const yAt = (value: number): number =>
    PADDING.top + plotHeight * (1 - value / top);

  const linePath = (key: "paid_total" | "due_total"): string =>
    `M ${trend
      .map((point, index) => `${xAt(index)},${yAt(parseAmount(point[key]))}`)
      .join(" L ")}`;

  const paidLine = hasActuals ? linePath("paid_total") : null;
  const paidArea =
    paidLine !== null
      ? `${paidLine} L ${xAt(actualCount - 1)},${bottom} L ${xAt(0)},${bottom} Z`
      : null;
  const dueLine = hasActuals ? linePath("due_total") : null;
  const forecastLine = hasForecast
    ? `M ${forecast
        .map(
          (point, index) =>
            `${xAt(actualCount + index)},${yAt(parseAmount(point.expected_total))}`,
        )
        .join(" L ")}`
    : null;
  const boundaryX =
    hasActuals && hasForecast
      ? (xAt(actualCount - 1) + xAt(actualCount)) / 2
      : null;
  const xLabels = [
    ...trend.map((point) => point.period),
    ...forecast.map((point) => point.period),
  ];

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

        {/* Present boundary between actuals and forecast */}
        {boundaryX !== null && (
          <line
            x1={boundaryX}
            y1={PADDING.top}
            x2={boundaryX}
            y2={bottom}
            stroke="currentColor"
            strokeWidth={1.5}
            className="text-slate-300 dark:text-slate-600"
          />
        )}

        {/* Due line (dashed) */}
        {dueLine !== null && (
          <path
            d={dueLine}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeDasharray="6 4"
            className="text-slate-400 dark:text-slate-500"
          />
        )}

        {/* Paid area + line */}
        {paidArea !== null && <path d={paidArea} fill={`url(#${gradientId})`} />}
        {paidLine !== null && (
          <path
            d={paidLine}
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            className="text-emerald-500"
          />
        )}

        {/* Forecast line (dashed amber) */}
        {forecastLine !== null && (
          <path
            d={forecastLine}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeDasharray="6 4"
            strokeLinejoin="round"
            strokeLinecap="round"
            className="text-amber-500"
          />
        )}

        {/* Forecast dots with native tooltips */}
        {hasForecast &&
          forecast.map((point, index) => (
            <circle
              key={`forecast-${point.period}`}
              cx={xAt(actualCount + index)}
              cy={yAt(parseAmount(point.expected_total))}
              r={3}
              fill="currentColor"
              className="text-amber-500"
            >
              <title>
                {`${formatMonth(point.period)} · ${t("trendForecast")}: ${amountFormatter.format(parseAmount(point.expected_total))} ${currency}`}
              </title>
            </circle>
          ))}

        {/* Paid dots with native tooltips */}
        {hasActuals &&
          trend.map((point, index) => (
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
        {hasActuals &&
          trend.map((point, index) => (
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

        {/* X-axis month labels — rotated so all 12 fit on mobile widths */}
        {xLabels.map((period, index) => (
          <text
            key={`label-${index}-${period}`}
            x={xAt(index)}
            y={HEIGHT - 8}
            textAnchor="end"
            transform={`rotate(-45 ${xAt(index)} ${HEIGHT - 8})`}
            className="fill-slate-400 text-[11px] dark:fill-slate-500"
          >
            {formatMonth(period)}
          </text>
        ))}
      </svg>

      <div className="mt-1 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
        {hasActuals && (
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
            {t("trendPaid")}
          </span>
        )}
        {hasActuals && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-4 border-t-2 border-dashed border-slate-400 dark:border-slate-500" />
            {t("trendDue")}
          </span>
        )}
        {hasForecast && (
          <span
            data-testid="trend-legend-forecast"
            className="flex items-center gap-1.5"
          >
            <span className="h-0 w-4 border-t-2 border-dashed border-amber-500" />
            {t("trendForecast")}
          </span>
        )}
      </div>
    </div>
  );
}
