import { useMemo } from 'react'
import { Link } from 'react-router-dom'

import { useAccuracy, useDecision, useModels, useQuality } from '../api/hooks'
import { EChart } from '../charts/EChart'
import { curveOption, groupBiasOption, modelBarsOption } from '../charts/options/accuracy'
import { decisionOption } from '../charts/options/series'
import { GlassPanel } from '../components/GlassPanel'
import { Icon } from '../components/ui/Icon'
import { StatTile, StatusPill } from '../components/ui/ui'
import { gw, mw, pct, signedMw, signedPct, ukDay, ukTime } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useScope } from '../state/filters'
import { useTheme } from '../theme/context'
import s from './OverviewPage.module.css'

const STORY_DAY = '2026-01-15'

export default function OverviewPage() {
  const scope = useScope()
  const { tokens } = useTheme()
  const range = { first: scope.first, last: scope.last, matching: scope.matching }
  const enabled = Boolean(scope.first)
  const accuracy = useAccuracy({ ...range, horizon_h: 24 })
  const models = useModels({ ...range, auction: 'n2ex_da' })
  const quality = useQuality({ first: scope.first, last: scope.last })
  const decision = useDecision(
    { delivery_date: STORY_DAY, auction: 'n2ex_da', margin_min: 0, matching: scope.matching },
    enabled,
  )

  const a = accuracy.data?.data
  const m = models.data?.data
  const q = quality.data?.data
  const d = decision.data?.data
  const best = m
    ? [...m.scores].sort((x, y) => (x.mae_mw ?? Infinity) - (y.mae_mw ?? Infinity))[0]
    : undefined
  const ratioFactor =
    a?.summary.mean_forecast_mw && a.summary.mean_actual_mw
      ? a.summary.mean_forecast_mw / a.summary.mean_actual_mw - 1
      : null

  const decisionChart = useMemo(
    () =>
      d
        ? decisionOption(d.points, d.actuals_half_hourly, tokens, {
            showActual: true,
            showAdjusted: true,
            showBand: true,
          })
        : null,
    [d, tokens],
  )
  const levelChart = useMemo(
    () => (a ? groupBiasOption(a.by_forecast_level, tokens, 'What WINDFOR said') : null),
    [a, tokens],
  )
  const curveChart = useMemo(() => (a ? curveOption(a.curve, tokens, 24) : null), [a, tokens])
  const modelChart = useMemo(() => (m ? modelBarsOption(m.scores, tokens) : null), [m, tokens])

  const qualityOk = q ? q.missing_runs.length === 0 && q.incomplete_days === 0 : null

  return (
    <div className={s.page}>
      <section className={s.hero}>
        <div className={s.heroCopy}>
          <p className={s.kicker}>
            <span className={s.dot} aria-hidden /> GB day-ahead · wind · January 2026 pilot
          </p>
          <h1 className={s.title}>
            The public wind forecast,
            <br />
            <span className={s.titleSoft}>checked against the moment you buy.</span>
          </h1>
          <p className={s.lede}>
            Every day the desk buys tomorrow&apos;s power at gate closure, using a wind forecast
            nobody has checked. Windesk shows the exact forecast that was available at your gate,
            how wrong that forecast has been, and how big a buffer that error calls for, without
            using any information you wouldn&apos;t have had at the time.
          </p>
          <div className={s.ctas}>
            <Link to="/decision" className={s.ctaPrimary}>
              Open the decision view <Icon name="arrowRight" size={16} />
            </Link>
            <Link to="/accuracy" className={s.ctaGhost}>
              See the accuracy analysis
            </Link>
          </div>
        </div>

        <div className={s.kpis}>
          <GlassPanel>
            <StatTile
              size="l"
              label="WINDFOR runs high by"
              value={ratioFactor != null ? `+${pct(ratioFactor)}` : '—'}
              detail={a ? `Bias ${signedMw(a.summary.bias_mw)} at day-ahead` : ' '}
            />
          </GlassPanel>
          <GlassPanel>
            <StatTile
              size="l"
              label="Typical day-ahead error"
              value={a ? gw(a.summary.mae_mw, 2) : '—'}
              detail="Mean absolute error, 24 h ahead"
            />
          </GlassPanel>
          <GlassPanel>
            <StatTile
              size="l"
              label="Error removed"
              value={best ? signedPct(best.skill_vs_raw) : '—'}
              detail="By a no-look-ahead ratio adjustment"
            />
          </GlassPanel>
          <GlassPanel>
            <StatTile
              size="l"
              label="80% range hit rate"
              value={m ? pct(m.band.coverage) : '—'}
              detail="Out of sample, at the N2EX gate"
            />
          </GlassPanel>
        </div>
      </section>

      <Reveal as="section" className={s.chapter}>
        <div className={s.chapterText}>
          <span className={s.num}>01</span>
          <h2>The forecast you could actually see</h2>
          <p>
            Delivery {ukDay(STORY_DAY)}. The N2EX auction closed at 09:50 the day before, and the
            newest WINDFOR run then
            {d?.run
              ? ` was published at ${ukTime(d.run.publish_time)}`
              : ' had been published shortly before'}
            . Windesk shows that run, the conservative P10 level to plan around, and, with
            hindsight, what actually happened.
          </p>
          <Link to={`/decision?day=${STORY_DAY}`} className={s.inlineLink}>
            Explore any delivery day <Icon name="arrowRight" size={14} />
          </Link>
        </div>
        <div className={s.chapterViz}>
          {decisionChart && (
            <EChart
              option={decisionChart}
              label={`Forecast, range and outturn for ${ukDay(STORY_DAY)}`}
              height={320}
            />
          )}
        </div>
      </Reveal>

      <Reveal as="section" className={s.chapter}>
        <div className={s.chapterText}>
          <span className={s.num}>02</span>
          <h2>It runs high, and more so in strong wind</h2>
          <p>
            Grouped by what the forecast said, WINDFOR comes in about{' '}
            {ratioFactor != null ? pct(ratioFactor) : '15%'} above metered outturn at every level,
            with a much bigger gap when it predicts strong wind, the hours when curtailment is most
            likely. Treating the forecast at face value leaves the desk short.
          </p>
          <Link to="/accuracy" className={s.inlineLink}>
            Break the error down <Icon name="arrowRight" size={14} />
          </Link>
        </div>
        <div className={s.chapterViz}>
          {levelChart && <EChart option={levelChart} label="Bias by forecast level" height={300} />}
        </div>
      </Reveal>

      <Reveal as="section" className={s.chapter}>
        <div className={s.chapterText}>
          <span className={s.num}>03</span>
          <h2>Error grows with horizon</h2>
          <p>
            Mean absolute error rises from {a ? mw(a.curve[1]?.mae_mw) : '—'} one hour ahead to{' '}
            {a ? mw(a.curve[24]?.mae_mw) : '—'} at day-ahead and {a ? mw(a.curve[48]?.mae_mw) : '—'}{' '}
            at two days. A desk buying at 09:50 for the evening peak is working with forecasts 30+
            hours old.
          </p>
          <Link to="/explorer" className={s.inlineLink}>
            Slide through horizons <Icon name="arrowRight" size={14} />
          </Link>
        </div>
        <div className={s.chapterViz}>
          {curveChart && <EChart option={curveChart} label="Error by horizon" height={300} />}
        </div>
      </Reveal>

      <Reveal as="section" className={s.chapter}>
        <div className={s.chapterText}>
          <span className={s.num}>04</span>
          <h2>Most of the error can be planned for</h2>
          <p>
            Adjusting each day using only errors already known at its gate cuts MAE from{' '}
            {m ? mw(m.scores.find((x) => x.model === 'raw')?.mae_mw) : '—'} to{' '}
            {best ? mw(best.mae_mw) : '—'}. The 80% range catches the outturn{' '}
            {m ? pct(m.band.coverage) : '—'} of the time, a buffer the desk can size with
            confidence.
          </p>
          <Link to="/models" className={s.inlineLink}>
            Compare methods <Icon name="arrowRight" size={14} />
          </Link>
        </div>
        <div className={s.chapterViz}>
          {modelChart && <EChart option={modelChart} label="MAE by method" height={240} />}
        </div>
      </Reveal>

      <Reveal as="section" className={s.trust}>
        <h2>Built to be trusted</h2>
        <div className={s.principles}>
          <div>
            <h3>No look-ahead, ever</h3>
            <p>
              Every figure uses only runs and outturn published before the decision. Property-based
              tests enforce this.
            </p>
          </div>
          <div>
            <h3>Traceable to source</h3>
            <p>
              Raw Elexon responses are stored as a versioned snapshot. Any chart can be exported as
              the exact forecast/actual pairs behind it.
            </p>
          </div>
          <div>
            <h3>Standard method</h3>
            <p>
              Bias, MAE, RMSE, error ranges and ramp scores follow the published protocol for
              evaluating wind forecasts. The method is documented in the app.
            </p>
          </div>
          <div>
            <h3>Data quality checked</h3>
            <p>
              {qualityOk == null ? (
                'Checking…'
              ) : (
                <StatusPill tone={qualityOk ? 'good' : 'warning'}>
                  {qualityOk ? 'All checks pass' : 'See issues'}
                </StatusPill>
              )}{' '}
              {q
                ? `${q.runs_total} runs, ${q.late_runs.length} late, every settlement period present.`
                : ''}
            </p>
            <Link to="/quality" className={s.inlineLink}>
              View checks <Icon name="arrowRight" size={14} />
            </Link>
          </div>
        </div>
      </Reveal>
    </div>
  )
}
