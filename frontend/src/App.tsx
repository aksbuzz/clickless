import { Routes, Route, Navigate } from 'react-router';
import { Layout } from './components/Layout';
import { WorkflowsPage } from './pages/WorkflowsPage';
import { WorkflowDetailPage } from './pages/WorkflowDetailPage';
import { WorkflowBuilderPage } from './pages/WorkflowBuilderPage';
import { InstancesPage } from './pages/InstancesPage';
import { InstanceDetailPage } from './pages/InstanceDetailPage';
import { ConnectorsPage } from './pages/ConnectorsPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/workflows" replace />} />
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="workflows/new" element={<WorkflowBuilderPage />} />
        <Route path="workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="workflows/:id/edit" element={<WorkflowBuilderPage />} />
        <Route path="instances" element={<InstancesPage />} />
        <Route path="instances/:id" element={<InstanceDetailPage />} />
        <Route path="connectors" element={<ConnectorsPage />} />
      </Route>
    </Routes>
  );
}
