import defaultTheme from 'tailwindcss/defaultTheme'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter Variable', ...defaultTheme.fontFamily.sans],
      },
      // Referência GovTech / transparência (uso opcional além das utilities padrão)
      colors: {
        'gov-navy': '#071D41',
        'gov-blue': '#1351B4',
      },
    },
  },
  plugins: [],
}
