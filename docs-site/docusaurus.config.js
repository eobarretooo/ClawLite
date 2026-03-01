// @ts-check

const config = {
  title: 'ClawLite',
  tagline: 'O assistente de IA mais poderoso para Linux e Termux',
  favicon: 'img/logo.svg',

  url: 'https://eobarretooo.github.io',
  baseUrl: '/ClawLite/',

  organizationName: 'eobarretooo',
  projectName: 'ClawLite',

  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'pt-br',
    locales: ['pt-br', 'en'],
    localeConfigs: {
      'pt-br': {label: 'Português (Brasil)'},
      en: {label: 'English'},
    },
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
        language: ['en', 'pt'],
      },
    ],
  ],

  themeConfig: {
    navbar: {
      title: 'ClawLite',
      items: [
        {to: '/getting-started', label: 'Início Rápido', position: 'left'},
        {to: '/instalacao', label: 'Instalação', position: 'left'},
        {to: '/comandos-cli', label: 'CLI', position: 'left'},
        {to: '/skills-reference', label: 'Skills', position: 'left'},
        {to: '/gateway-api', label: 'Gateway', position: 'left'},
        {to: '/faq', label: 'FAQ', position: 'left'},
        {type: 'localeDropdown', position: 'right'},
        {href: 'https://github.com/eobarretooo/ClawLite', label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentação',
          items: [
            {label: 'Começando em 1 minuto', to: '/getting-started'},
            {label: 'Hub API', to: '/hub-api'},
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
