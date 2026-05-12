/** Dark Clerk card aligned with Sloww tokens; V1 is email OTP — hide OAuth block when present. */
export const clerkAppearance = {
  baseTheme: undefined,
  variables: {
    colorPrimary: 'oklch(0.62 0.24 292)',
    colorBackground: 'oklch(0.14 0.02 280)',
    colorInputBackground: 'oklch(0.18 0.025 280)',
    colorText: 'oklch(0.93 0.01 280)',
    colorTextSecondary: 'oklch(0.62 0.02 280)',
    colorDanger: 'oklch(0.58 0.2 25)',
    borderRadius: '12px',
    fontFamily: '"Outfit", system-ui, sans-serif',
    fontFamilyButtons: '"Outfit", system-ui, sans-serif',
  },
  elements: {
    rootBox: { width: '100%' },
    card: {
      backgroundColor: 'oklch(0.16 0.025 280)',
      border: '1px solid oklch(0.28 0.04 280)',
      boxShadow: 'none',
    },
    headerTitle: { fontFamily: '"Space Grotesk", system-ui, sans-serif' },
    socialButtonsRoot: { display: 'none' },
    dividerRow: { display: 'none' },
    formButtonPrimary: {
      fontWeight: '600',
      fontSize: '0.95rem',
      background: 'oklch(0.56 0.21 292)',
      border: '1px solid oklch(0.5 0.18 292)',
    },
  },
} as const
