const markdownPath = process.env.MARKDOWN_PATH || null;

const content = [
  "./scribe/templates/*.{html,js}",
  ...(markdownPath ? [`${markdownPath}/**/*.md`] : []),
];

console.log("Building styles based on these files: ", content.join(" | "));

module.exports = {
  content,
  safelist: [
    "Color-Black",
    "-Color-Red",
    "-Color-Green",
    "-Color-Yellow",
    "-Color-Blue",
    "-Color-Magneta",
    "-Color-Cyan",
    "-Color-White",
    /* Inline image styles */
    "shadow-lg",
    "border-white",
    "border-4",
    "rounded-lg",
    "lg:max-w-[100vw]",
    "lg:-ml-[125px]",
    "xl:-ml-[250px]",
    "lg:w-offset-content-image-lg",
    "xl:w-offset-content-image-xl",
  ],
  darkMode: "class",
  theme: {
    extend: {
      width: {
        "offset-content-image-lg": "calc(100% + 250px)",
        "offset-content-image-xl": "calc(100% + 400px)",
      },
      typography: ({ theme }) => ({
        DEFAULT: {
          css: {
            fontFamily: '"PT Serif", ui-serif, Cambria, "Times New Roman", Times, serif',
            fontFeatureSettings: 'normal',
            fontVariationSettings: 'normal',
            //'--tw-prose-body': theme('colors.gray[700]'),
            "--tw-prose-links": theme("colors.blue[500]"),
            "--tw-prose-invert-links": theme("colors.blue[300]"),
            "--tw-prose-quotes": theme("colors.gray[500]"),
            "--tw-prose-invert-body": theme("colors.gray[200]"),
            a: {
              textDecoration: "none",
              fontWeight: "500",
            },
            h2: {
              marginTop: "0px",
            },
            ul: {
              marginBottom: "1em",
            },
            img: {
              borderRadius: theme("rounded"),
            },
            figcaption: {
              textAlign: "center",
            },
          },
        },
      }),
    },
  },
  plugins: [require("@tailwindcss/typography"), require("@tailwindcss/forms")],
};
