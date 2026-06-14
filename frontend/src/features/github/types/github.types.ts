export interface GitIntegrationRead {
  id: string
  project_id: string
  github_app_installation_id: string
  repo_full_name: string
  default_branch: string
  created_at: string
  updated_at: string
}

export interface GitInstallUrlResponse {
  install_url: string
}