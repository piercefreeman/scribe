module.exports = {
  content: [
    "./scribe/components/*.{html,js}",
    "./scribe/templates/*.{html,js}",
    // include markdown docs that might have some custom html markup within them
    "../public/**/*.md"
  ],
  safelist: [
    "Color-Black",
    "-Color-Red",
    "-Color-Green",
    "-Color-Yellow",
    "-Color-Blue",
    "-Color-Magneta",
    "-Color-Cyan",
    "-Color-White",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      typography: ({ theme }) => ({
        DEFAULT: {
          css: {
            //'--tw-prose-body': theme('colors.gray[700]'),
            '--tw-prose-links': theme('colors.blue[500]'),
            '--tw-prose-invert-links': theme('colors.blue[300]'),
            '--tw-prose-quotes': theme('colors.gray[500]'),
            a: {
              textDecoration: 'none',
              fontWeight: '500',
            },
            p: {
              //lineHeight: '1.6em',
              //fontSize: '17px',
              fontSize: '1.1rem',
            },
            ul: {
              fontSize: '1.1rem',
            },
            img: {
              borderRadius: theme('rounded'),
            },
            figcaption: {
              textAlign: 'center',
            }
          },
        },
      }),
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
