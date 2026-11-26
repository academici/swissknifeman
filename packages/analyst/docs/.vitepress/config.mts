import { defineConfig } from 'vitepress'

// Standalone-dock config analyst. In the umbrella unit this .vitepress deleted
// (scripts/docs-sync.sh), the site is going to be shared docs/.vitepress. Internal links
// docks — relative (work and standalone, and in the unit); cross-batch
// (/maind/, /skiller/, /harness/, /routing, /roadmap) V standalone dead → ignoreDeadLinks.
export default defineConfig({
  lang: 'en-US',
  title: 'analyst',
  description:
    'Continuous learning ecosystems academici: deterministic capture of lessons from runs with a human in the gate',
  base: '/analyst/',
  lastUpdated: true,

  ignoreDeadLinks: [/^\/harness\//, /^\/maind\//, /^\/skiller\//, /^\/routing/, /^\/roadmap\b/,
    /^\/reference/],

  themeConfig: {
    nav: [
      { text: 'Hyde', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Architecture', link: '/architecture', activeMatch: '/architecture' },
      { text: 'Roadmap', link: '/roadmap', activeMatch: '/roadmap' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Getting started',
          items: [
            { text: 'About analyst', link: '/guide/' },
            { text: 'Package architecture', link: '/architecture' },
          ],
        },
        {
          text: 'How does this work',
          items: [
            { text: 'CLI and commands', link: '/guide/cli' },
            { text: 'Lesson life cycle', link: '/guide/lifecycle' },
            { text: 'Pathology catalog', link: '/guide/pathologies' },
            { text: 'Tuning-parameters', link: '/guide/tuning' },
            { text: 'suggest — skill draft (P4)', link: '/guide/suggest' },
          ],
        },
        {
          text: 'Roadmap',
          items: [{ text: 'Deferred (P5)', link: '/roadmap' }],
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/academici/swissknifeman' },
    ],

    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: 'Search', buttonAriaLabel: 'Search' },
          modal: {
            noResultsText: 'Nothing found',
            resetButtonTitle: 'Reset',
            footer: { selectText: 'choose', navigateText: 'navigation', closeText: 'close' },
          },
        },
      },
    },

    outline: { label: 'On this page' },
    docFooter: { prev: 'Back', next: 'Forward' },
    lastUpdated: { text: 'Updated' },
    darkModeSwitchLabel: 'Subject',
    sidebarMenuLabel: 'Menu',
    returnToTopLabel: 'Top',
  },
})
