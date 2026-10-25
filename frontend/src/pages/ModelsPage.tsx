import { useMemo } from 'react'

import { useMeta, useModels } from '../api/hooks'
import type { AuctionId, ModelScore } from '../api/types'
import { EChart } from '../charts/EChart'
import {
  dailyModelOption,
  MODEL_LABEL,
  modelBarsOption,
  modelColor,
} from '../charts/options/accuracy'
import { ScopeFilters } from '../components/ScopeFilters'
import { DataTable, type Column } from '../components/ui/DataTable'
import {
  Button,
  Callout,
  Card,
  ErrorState,
  FilterBar,
  Grid,
  Loading,
  PageHeader,
  Segmented,
  StatTile,
  StatusPill,
} from '../components/ui/ui'
import { mw, pct, signedMw, signedPct } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useParam, useScope } from '../state/filters'
import { useTheme } from '../theme/context'
import s from './pages.module.css'

export default function ModelsPage() {
  const meta = useMeta().data?.data
  const scope = useScope()
  const [params, update] = useParam()
  const { tokens } = useTheme()
  const auction = (params.get('auction') ?? 'n2ex_da') as AuctionId
  const query = useModels({
    first: scope.first,
    last: scope.last,
    matching: scope.matching,
    auction,
  })
  const d = query.data?.data
  const bars = useMemo(() => (d ? modelBarsOption(d.scores, tokens) : null), [d, tokens])
  const daily = useMemo(() => (d ? dailyModelOption(d.daily, tokens) : null), [d, tokens])

  const best = d
    ? [...d.scores].sort((a, b) => (a.mae_mw ?? Infinity) - (b.mae_mw ?? Infinity))[0]
    : undefined
  const raw = d?.scores.find((m) => m.model === 'raw')
  const coverage = d?.band.coverage
  const coverageTone =
    coverage == null ? 'info' : Math.abs(coverage - d!.band.nominal) <= 0.07 ? 'good' : 'warning'

  const columns: Column<ModelScore>[] = [
    {
      key: 'm',
      header: 'Model',
      cell: (m) => (
        <span className={s.modelCell}>
          <i style={{ background: modelColor(tokens, m.model) }} aria-hidden />
          {MODEL_LABEL[m.model]}
        </span>
      ),
    },
    { key: 'mae', header: 'MAE', cell: (m) => mw(m.mae_mw), align: 'right' },
    { key: 'rmse', header: 'RMSE', cell: (m) => mw(m.rmse_mw), align: 'right' },
    { key: 'bias', header: 'Bias', cell: (m) => signedMw(m.bias_mw), align: 'right' },
    {
      key: 'sr',
      header: 'Skill vs WINDFOR',
      cell: (m) => signedPct(m.skill_vs_raw),
      align: 'right',
    },
    {
      key: 'sp',
      header: 'Skill vs persistence',
      cell: (m) => signedPct(m.skill_vs_persistence),
      align: 'right',
    },
  ]

  return (
    <>
      <PageHeader
        eyebrow="Out-of-sample evaluation"
        title="Can the error be planned around?"
        lede="Each delivery day is adjusted using only earlier days' errors that were already published at that day's gate, the same information a desk would have had live. The scores below are what these methods would actually have achieved."
      />
      <FilterBar>
        <Segmented<AuctionId>
          label="Gate closure"
          value={auction}
          onChange={(v) => update({ auction: v === 'n2ex_da' ? null : v })}
          options={(meta?.auctions ?? []).map((a) => ({
            value: a.id,
            label: `${a.name} · ${a.gate_local}`,
          }))}
        />
        <ScopeFilters />
      </FilterBar>

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {!d && query.isPending && <Loading />}
      {d && best && raw && (
        <>
          <Grid cols={3}>
            <Card>
              <StatTile
                size="l"
                label="Best method"
                accent={modelColor(tokens, best.model)}
                value={MODEL_LABEL[best.model]}
                detail={`MAE ${mw(best.mae_mw)} vs ${mw(raw.mae_mw)} as published`}
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="Error removed"
                value={signedPct(best.skill_vs_raw)}
                detail="MAE skill against raw WINDFOR, out of sample"
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="80% range hit rate"
                value={pct(coverage, 1)}
                detail={`${pct(d.band.below, 1)} below · ${pct(d.band.above, 1)} above · mean width ${mw(d.band.mean_width_mw)}`}
              />
              <div className={s.pillRow}>
                <StatusPill tone={coverageTone}>
                  {coverageTone === 'good' ? 'Well calibrated' : 'Check calibration'}
                </StatusPill>
              </div>
            </Card>
          </Grid>

          <Grid cols={2}>
            <Reveal>
              <Card
                title="Mean absolute error by method"
                subtitle={`${raw.n} delivery hours, scored only where every method has a value.`}
                actions={
                  <Button
                    icon="download"
                    href={`/api/export/pairs.csv?first=${scope.first}&last=${scope.last}&auction=${auction}&matching=${scope.matching}`}
                    download
                  >
                    CSV
                  </Button>
                }
              >
                {bars && (
                  <EChart
                    option={bars}
                    label="MAE by method"
                    height={220}
                    stale={query.isPlaceholderData}
                  />
                )}
                <DataTable
                  caption="Model scores"
                  columns={columns}
                  rows={d.scores}
                  rowKey={(m) => m.model}
                />
              </Card>
            </Reveal>
            <Reveal>
              <Card
                title="Day by day"
                subtitle="Daily MAE of WINDFOR as published and of both adjustments."
              >
                {daily && (
                  <EChart
                    option={daily}
                    label="Daily MAE by method"
                    height={340}
                    stale={query.isPlaceholderData}
                  />
                )}
              </Card>
            </Reveal>
          </Grid>

          <Grid cols={2}>
            <Callout tone="info" title="Why the ratio adjustment wins">
              The gap between WINDFOR and FUELHH grows with wind output (about 15% everywhere, more
              in strong winds). Dividing by the trailing energy ratio captures that; subtracting a
              constant does not.
            </Callout>
            <Callout tone="info" title="Persistence is a sanity floor">
              &ldquo;Tomorrow equals the last known outturn&rdquo; is the simplest possible
              forecast. Any forecast worth paying attention to should beat it comfortably, and
              WINDFOR does.
            </Callout>
          </Grid>
        </>
      )}
    </>
  )
}
