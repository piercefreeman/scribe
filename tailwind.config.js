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
            '--tw-prose-invert-body': theme('colors.gray[200]'),
            a: {
              textDecoration: 'none',
              fontWeight: '500',
            },
            p: {
              fontSize: "20px",
              lineHeight: 1.7
            },
            ul: {
              fontSize: "20px",
            },
            ol: {
              fontSize: "20px",
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
    require('@tailwindcss/forms'),
  ],
}
