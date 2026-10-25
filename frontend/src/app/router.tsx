import { lazy, Suspense } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { Loading } from '../components/ui/ui'
import { AppShell } from './AppShell'
import { NotFound } from './NotFound'

// Each page is its own chunk; the overview loads first.
const OverviewPage = lazy(() => import('../pages/OverviewPage'))
const DecisionPage = lazy(() => import('../pages/DecisionPage'))
const ExplorerPage = lazy(() => import('../pages/ExplorerPage'))
const AccuracyPage = lazy(() => import('../pages/AccuracyPage'))
const ModelsPage = lazy(() => import('../pages/ModelsPage'))
const RampsPage = lazy(() => import('../pages/RampsPage'))
const QualityPage = lazy(() => import('../pages/QualityPage'))

const page = (node: ReactNode) => <Suspense fallback={<Loading />}>{node}</Suspense>

const routes = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: page(<OverviewPage />) },
      { path: 'decision', element: page(<DecisionPage />) },
      { path: 'explorer', element: page(<ExplorerPage />) },
      { path: 'accuracy', element: page(<AccuracyPage />) },
      { path: 'models', element: page(<ModelsPage />) },
      { path: 'ramps', element: page(<RampsPage />) },
      { path: 'quality', element: page(<QualityPage />) },
      { path: '*', element: <NotFound /> },
    ],
  },
]

const router = createBrowserRouter(routes)

export function AppRouter() {
  return <RouterProvider router={router} />
}
