import { useEffect, useRef } from 'react'

import { useMeta } from '../api/hooks'
import { Icon } from '../components/ui/Icon'
import { useMotion } from '../motion/context'
import s from './MethodologyDrawer.module.css'

/**
 * How every number is made, in plain language. Opened from the nav on any
 * page; Escape or the backdrop closes it and focus returns to the trigger.
 */
export function MethodologyDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const panel = useRef<HTMLDivElement | null>(null)
  const returnFocus = useRef<Element | null>(null)
  const { getLenis } = useMotion()
  const meta = useMeta().data?.data

  useEffect(() => {
    if (!open) return
    returnFocus.current = document.activeElement
    panel.current?.focus()
    const lenis = getLenis()
    lenis?.stop()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      lenis?.start()
      if (returnFocus.current instanceof HTMLElement) returnFocus.current.focus()
    }
  }, [open, onClose, getLenis])

  if (!open) return null
  return (
    <div className={s.root}>
      <div className={s.backdrop} onClick={onClose} aria-hidden />
      <div
        ref={panel}
        className={s.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="methodology-title"
        tabIndex={-1}
        data-lenis-prevent
      >
        <header className={s.head}>
          <h2 id="methodology-title">Methodology</h2>
          <button
            type="button"
            className={s.close}
            onClick={onClose}
            aria-label="Close methodology"
          >
            <Icon name="x" />
          </button>
        </header>

        <section>
          <h3>Data</h3>
          <p>
            <strong>Actuals</strong>: Elexon <code>FUELHH</code>, fuel type <code>WIND</code>.
            Half-hourly mean output of transmission-metered wind farms, after any curtailment.{' '}
            <strong>Forecasts</strong>: Elexon <code>WINDFOR</code>, the national wind forecast. It
            is hourly, published 8 times a day (02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and
            22:30 UTC), and each run looks up to about 66 hours ahead.
          </p>
          <p>
            Raw API responses are stored as an immutable snapshot. Every response from this app
            carries its <code>data_version</code>
            {meta && (
              <>
                {' '}
                (currently <code>{meta.data_version}</code>)
              </>
            )}
            , so any figure can be traced back to its source.
          </p>
        </section>

        <section>
          <h3>No look-ahead</h3>
          <p>
            For each target hour, the forecast used is the run with the latest publish time at or
            before the cutoff. The run must also contain that hour. In the <em>Decision</em> view,
            the cutoff is the auction gate closure on the day before delivery, minus an optional
            safety margin. In the <em>Horizon</em> view, it is the target time minus the chosen
            horizon. A run published after the cutoff is never used. Property-based tests check this
            on randomly generated histories.
          </p>
        </section>

        <section>
          <h3>Matching hourly forecasts to half-hourly actuals</h3>
          <p>
            By default, each forecast hour is compared with the mean of its two half-hours (
            <code>HH:00</code> and <code>HH:30</code>), so both sides describe the same energy.
            Hours with only one half-hour are dropped. The alternative compares only the{' '}
            <code>HH:00</code> period. Every analysis view lets you pick the rule.
          </p>
        </section>

        <section>
          <h3>Error metrics</h3>
          <dl className={s.defs}>
            <dt>Error</dt>
            <dd>
              Forecast − actual, in MW. A positive error means less wind arrived than forecast, so
              the buyer was short.
            </dd>
            <dt>Bias</dt>
            <dd>Mean error. It shows systematic over- or under-forecasting.</dd>
            <dt>MAE / RMSE</dt>
            <dd>
              Mean absolute error, and root-mean-square error, which weights large misses more
              heavily.
            </dd>
            <dt>WAPE</dt>
            <dd>
              Total absolute error ÷ total actual output. MAPE is not reported: it divides by output
              and blows up in calm hours.
            </dd>
            <dt>nMAE</dt>
            <dd>
              MAE ÷ capacity proxy. Installed capacity is not in the data, so the highest observed
              outturn is used. This makes nMAE conservative (slightly too high).
            </dd>
            <dt>P10–P90</dt>
            <dd>The range covering the middle 80% of errors.</dd>
          </dl>
        </section>

        <section>
          <h3>Bias adjustment and error bands</h3>
          <p>
            Each delivery day is fitted only on earlier days (by default the previous{' '}
            {meta?.trailing_days ?? 28} days), using only outturn already published by that
            day&apos;s cutoff. The <em>ratio adjustment</em> divides the forecast by the trailing
            ratio of forecast to actual energy. The <em>additive</em> variant subtracts the trailing
            median error for that 6-hour block of the day. The P10–P90 band comes from trailing
            error quantiles by 6-hour block. Coverage and skill are measured out of sample, so they
            show how the method would have performed live.
          </p>
        </section>

        <section>
          <h3>Known limits</h3>
          <ul>
            <li>
              <code>WINDFOR</code> runs about 15% above <code>FUELHH</code>. Likely causes are
              curtailment and differences in which wind farms each dataset covers, but testing this
              needs balancing-action data, which is outside this pilot&apos;s scope.
            </li>
            <li>
              <code>FUELHH</code> leaves out wind connected to local distribution networks, so it is
              not the total GB wind output.
            </li>
            <li>
              The EPEX 60-minute gate time comes from a secondary source. You can set any gate time
              manually.
            </li>
          </ul>
        </section>

        <section>
          <h3>Sources</h3>
          <ul>
            <li>
              <a
                href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream"
                target="_blank"
                rel="noreferrer"
              >
                Elexon FUELHH stream
              </a>
              {' · '}
              <a
                href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream"
                target="_blank"
                rel="noreferrer"
              >
                Elexon WINDFOR stream
              </a>
            </li>
            <li>
              Madsen, Pinson, Kariniotakis et al. (2005),{' '}
              <em>
                Standardizing the performance evaluation of short-term wind power prediction models
              </em>
              .
            </li>
          </ul>
        </section>
      </div>
    </div>
  )
}
