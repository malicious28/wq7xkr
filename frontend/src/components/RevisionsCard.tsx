import { useMemo } from 'react'

import { useRevisions, type DecisionParams } from '../api/hooks'
import { EChart } from '../charts/EChart'
import { revisionsOption, revisionSummary } from '../charts/options/revisions'
import { signedMw, ukDay } from '../lib/format'
import { useTheme } from '../theme/context'
import { Card, ErrorState, Loading } from './ui/ui'

/** Every WINDFOR run that covered the delivery day, and how far they moved. */
export function RevisionsCard({
  params,
  hindsight,
}: {
  params: DecisionParams
  hindsight: boolean
}) {
  const { tokens } = useTheme()
  const query = useRevisions(params)
  const d = query.data?.data
  const option = useMemo(
    () => (d ? revisionsOption(d.runs, d.actual, d.used_publish_time, tokens, hindsight) : null),
    [d, tokens, hindsight],
  )
  const summary = d ? revisionSummary(d.runs, d.used_publish_time) : null
  const before = d ? d.runs.filter((r) => r.available).length : 0

  return (
    <Card
      title="How the forecast moved"
      subtitle={
        d && summary
          ? `${summary.runs} runs covered ${ukDay(d.delivery_date)}; ${before} were published before the gate. ` +
            (summary.firstToUsedMw == null
              ? ''
              : `By the run used at the gate, the forecast had moved ${signedMw(summary.firstToUsedMw)} on average from the first run (over the ${summary.commonHours} hours both cover).`)
          : 'Every forecast run that covered this delivery day.'
      }
      footer="Older runs are fainter. Dashed runs arrived after the gate and could not be used for this decision."
    >
      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {!d && query.isPending && <Loading label="Loading runs" />}
      {option && d && (
        <EChart
          option={option}
          label={`All ${d.runs.length} forecast runs for ${ukDay(d.delivery_date)}, with the run used at the gate highlighted`}
          height={320}
          stale={query.isPlaceholderData}
        />
      )}
    </Card>
  )
}
