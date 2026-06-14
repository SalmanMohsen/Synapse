import { api } from '@/shared/lib/axios'
import type { GitInstallUrlResponse, GitIntegrationRead } from '../types/github.types'

export const githubApi = {
  getIntegration: (projectId: string): Promise<GitIntegrationRead> =>
    api.get<GitIntegrationRead>(`/projects/${projectId}/github`).then((r) => r.data),

  getInstallUrl: (projectId: string): Promise<GitInstallUrlResponse> =>
    api.get<GitInstallUrlResponse>(`/projects/${projectId}/github/install`).then((r) => r.data),

  deleteIntegration: (projectId: string): Promise<void> =>
    api.delete(`/projects/${projectId}/github`).then(() => undefined),
}