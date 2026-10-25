import type { MatchingRule } from '../api/types'
import { useScope } from '../state/filters'
import { Field, Segmented, Select } from './ui/ui'

const MATCHING_LABEL: Record<MatchingRule, string> = {
  hour_mean: 'Hour mean (HH:00 + HH:30)',
  on_the_hour: 'On the hour (HH:00 only)',
}

/** Scope + matching rule: the two filters every analysis view shares. */
export function ScopeFilters({ showMatching = true }: { showMatching?: boolean }) {
  const scope = useScope()
  if (!scope.presets.length) return null
  return (
    <>
      <Segmented
        label="Scope"
        value={scope.preset?.id ?? ''}
        onChange={scope.setScope}
        options={scope.presets.map((p) => ({
          value: p.id,
          label: p.id.startsWith('decisions') ? 'Decisions in Jan' : 'Delivery in Jan',
          title: p.description,
        }))}
      />
      {showMatching && (
        <Field label="Matching rule">
          {(id) => (
            <Select
              id={id}
              value={scope.matching}
              onChange={scope.setMatching}
              options={(Object.keys(MATCHING_LABEL) as MatchingRule[]).map((m) => ({
                value: m,
                label: MATCHING_LABEL[m],
              }))}
            />
          )}
        </Field>
      )}
    </>
  )
}
