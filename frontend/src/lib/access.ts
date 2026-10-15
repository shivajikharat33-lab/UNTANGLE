export function gateNeeded(config: { access_required?: boolean } | null | undefined): boolean {
  return config?.access_required === true;
}

export function uploadsHidden(config: { public_demo_mode?: boolean } | null | undefined): boolean {
  return config?.public_demo_mode === true;
}
