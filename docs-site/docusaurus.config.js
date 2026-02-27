// @ts-check

const config = {
  title: 'ClawLite',
  tagline: 'Portable AI assistant for Linux + Termux',
  favicon: 'img/logo.svg',

  url: 'https://eobarretooo.github.io',
  baseUrl: '/ClawLite/',

  organizationName: 'eobarretooo',
  projectName: 'ClawLite',

  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: require.resolve('./sidebars.js'),
          routeBasePath: '/',
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      },
    ],
  ],

  themes: [
    [
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        docsRouteBasePath: '/',
        language: ['en'],
      },
    ],
  ],

  themeConfig: {
    navbar: {
      title: 'ClawLite',
      items: [
        {to: '/getting-started', label: 'Getting Started', position: 'left'},
        {to: '/configuration', label: 'Configuration', position: 'left'},
        {to: '/skills-reference', label: 'Skills', position: 'left'},
        {to: '/gateway-api', label: 'Gateway API', position: 'left'},
        {href: 'https://github.com/eobarretooo/ClawLite', label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Getting Started', to: '/getting-started'},
            {label: 'Gateway API', to: '/gateway-api'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} ClawLite`,
    },
    colorMode: {
      defaultMode: 'dark',
      disableSwitch: false,
      respectPrefersColorScheme: true,
    },
  },
};

module.exports = config;
