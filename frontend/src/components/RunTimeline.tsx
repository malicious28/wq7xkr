import type { RunInfo } from '../api/types'
import { ukDateTime, ukTime, ukWallClockMs } from '../lib/format'
import s from './RunTimeline.module.css'

interface RunTimelineProps {
  runs: RunInfo[]
  chosen: RunInfo | null
  cutoff: string
  deliveryStart: string
  deliveryEnd: string
}

const W = 1000
const H = 92

/**
 * Which forecast runs existed before the gate? Runs are ticks on a timeline
 * from 24 h before the cutoff to the end of delivery: filled = usable,
 * hollow = arrived after the gate, ringed = the run the desk would have used.
 */
export function RunTimeline({
  runs,
  chosen,
  cutoff,
  deliveryStart,
  deliveryEnd,
}: RunTimelineProps) {
  const t0 = ukWallClockMs(cutoff) - 24 * 3_600_000
  const t1 = ukWallClockMs(deliveryEnd)
  const x = (iso: string) => ((ukWallClockMs(iso) - t0) / (t1 - t0)) * (W - 40) + 20
  const gateX = x(cutoff)
  const dStart = x(deliveryStart)
  const dEnd = x(deliveryEnd)

  return (
    <figure className={s.figure}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className={s.svg}
        role="img"
        aria-label={`Forecast runs around the gate closure at ${ukTime(cutoff)} UK`}
      >
        <rect x={dStart} y={18} width={dEnd - dStart} height={44} rx={8} className={s.delivery} />
        <text x={dStart + 10} y={34} className={s.deliveryLabel}>
          Delivery day
        </text>
        <line x1={20} x2={W - 20} y1={52} y2={52} className={s.axis} />
        <rect x={20} y={46} width={gateX - 20} height={12} rx={6} className={s.known} />
        {runs.map((r) => {
          const cx = x(r.publish_time)
          const isChosen = chosen?.publish_time === r.publish_time
          return (
            <g key={r.publish_time}>
              <title>{`${ukDateTime(r.publish_time)} UK${r.available ? '' : ' (after gate)'}${r.late ? `, ${Math.round(r.delay_min)} min late` : ''}`}</title>
              {isChosen && <circle cx={cx} cy={52} r={11} className={s.chosenRing} />}
              <circle
                cx={cx}
                cy={52}
                r={5.5}
                className={r.available ? s.runAvailable : s.runLater}
              />
              {r.late && <circle cx={cx} cy={52} r={2} className={s.lateDot} />}
            </g>
          )
        })}
        <line x1={gateX} x2={gateX} y1={8} y2={78} className={s.gate} />
        <text x={gateX} y={90} textAnchor="middle" className={s.gateLabel}>
          Gate {ukTime(cutoff)}
        </text>
      </svg>
      <figcaption className={s.legend}>
        <span>
          <i className={s.keyAvailable} /> Run available at gate
        </span>
        <span>
          <i className={s.keyLater} /> Published after gate
        </span>
        <span>
          <i className={s.keyChosen} /> Run used
        </span>
      </figcaption>
    </figure>
  )
}
