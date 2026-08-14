// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// Primary domain is k8squad.io (GitHub Pages, custom domain via public/CNAME).
// Served at the domain root, so `base` stays '/'.
export default defineConfig({
  site: 'https://k8squad.io',
  integrations: [
    starlight({
      title: 'K8squad',
      description:
        'Kubernetes-native, agent-agnostic control plane for running a squad of AI agents against a shared backlog.',
      logo: {
        dark: './src/assets/mark-8crest-on-dark.svg',
        light: './src/assets/mark-8crest-on-light.svg',
        replacesTitle: false,
      },
      favicon: '/favicon.svg',
      customCss: ['./src/styles/theme.css'],
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/K8squad' },
      ],
      // Geist Sans (UI) + Geist Mono (code), per the locked brand contract.
      head: [
        { tag: 'link', attrs: { rel: 'preconnect', href: 'https://fonts.googleapis.com' } },
        {
          tag: 'link',
          attrs: { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: true },
        },
        {
          tag: 'link',
          attrs: {
            rel: 'stylesheet',
            href: 'https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap',
          },
        },
      ],
      // Docs live under the /docs URL prefix (content mirrored to
      // src/content/docs/docs by scripts/sync-content.mjs). `/` is the custom
      // landing page in src/pages/index.astro.
      sidebar: [
        { label: 'Quickstart', link: '/docs/quickstart' },
        { label: 'Concepts', autogenerate: { directory: 'docs/concepts' } },
        { label: 'Operator Guide', autogenerate: { directory: 'docs/operator-guide' } },
        { label: 'Author Guide', autogenerate: { directory: 'docs/author-guide' } },
        { label: 'Console Guide', link: '/docs/console-guide' },
        { label: 'API Reference', link: '/docs/api-reference' },
        { label: 'Observability', link: '/docs/observability' },
        { label: 'Plugin SDK', autogenerate: { directory: 'docs/plugin-sdk' } },
        { label: 'Troubleshooting', link: '/docs/troubleshooting' },
      ],
    }),
  ],
});
