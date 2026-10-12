/* @ds-bundle: {"format":3,"namespace":"MadisonGroupEnterprisesDesignSystem_b6110c","components":[],"sourceHashes":{"ui_kits/mge/Banner.jsx":"da96f319f760","ui_kits/mge/BusinessGrid.jsx":"5af204cba1d2","ui_kits/mge/Button.jsx":"816738d01279","ui_kits/mge/ContactBlock.jsx":"64dc5cd4dfad","ui_kits/mge/Footer.jsx":"1c44b29f7c85","ui_kits/mge/Header.jsx":"f21d686a5b90","ui_kits/mge/IndustryStrip.jsx":"11aa44337ba1"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.MadisonGroupEnterprisesDesignSystem_b6110c = window.MadisonGroupEnterprisesDesignSystem_b6110c || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// ui_kits/mge/Banner.jsx
try { (() => {
function Banner({
  eyebrow,
  title,
  subtitle,
  ctas = [],
  size = 'large',
  dark = true,
  imageBg
}) {
  const h = {
    compact: 180,
    standard: 300,
    large: 450
  }[size];
  return /*#__PURE__*/React.createElement("section", {
    style: {
      position: 'relative',
      height: h,
      background: dark ? '#2e3c49' : '#fff',
      color: dark ? '#fff' : '#2e3c49',
      overflow: 'hidden'
    }
  }, imageBg && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      backgroundImage: `url(${imageBg})`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      opacity: .35
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      backgroundImage: 'url(../../assets/banner-overlay.png)',
      backgroundSize: 'cover',
      backgroundPosition: '100% 50%',
      opacity: .1,
      pointerEvents: 'none'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      maxWidth: 1320,
      margin: '0 auto',
      padding: '0 24px',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center'
    }
  }, eyebrow && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      textTransform: 'uppercase',
      letterSpacing: '.12em',
      color: dark ? '#909dab' : '#909dab',
      marginBottom: 10
    }
  }, eyebrow), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 44,
      fontWeight: 600,
      lineHeight: 1.1,
      margin: 0,
      maxWidth: 520,
      padding: 0
    }
  }, title, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#e31837'
    }
  }, ".")), subtitle && /*#__PURE__*/React.createElement("p", {
    style: {
      marginTop: 14,
      fontSize: 15,
      lineHeight: 1.6,
      maxWidth: 460,
      color: dark ? '#c8cfd6' : '#445c6d'
    }
  }, subtitle), ctas.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 24,
      display: 'flex',
      gap: 14,
      flexWrap: 'wrap'
    }
  }, ctas.map((c, i) => /*#__PURE__*/React.createElement(Button, {
    key: i,
    variant: c.variant || (i === 0 ? 'red' : 'outlineWhite'),
    onClick: c.onClick
  }, c.label)))));
}
window.Banner = Banner;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/mge/Banner.jsx", error: String((e && e.message) || e) }); }

// ui_kits/mge/BusinessGrid.jsx
try { (() => {
function BusinessGrid({
  items,
  columns = 4,
  title,
  affiliated = false
}) {
  // red-corner checkerboard: even-indexed tiles get the red corner (matches the SCSS pattern)
  return /*#__PURE__*/React.createElement("section", {
    style: {
      background: affiliated ? '#e4e5e6' : '#f7f7f8',
      padding: '60px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '0 24px'
    }
  }, title && /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 32,
      fontWeight: 600,
      margin: '0 0 36px',
      color: '#2e3c49',
      padding: 0
    }
  }, title, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#e31837'
    }
  }, ".")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: `repeat(${columns},1fr)`,
      gap: 14
    }
  }, items.map((it, i) => {
    const rc = i % 2 === 1;
    return /*#__PURE__*/React.createElement("a", {
      key: it.name,
      style: {
        position: 'relative',
        background: '#fff',
        padding: 30,
        minHeight: 200,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        transition: 'box-shadow 200ms',
        cursor: 'pointer',
        textDecoration: 'none'
      },
      onMouseEnter: e => e.currentTarget.style.boxShadow = '0 0 7px 0 #e31837',
      onMouseLeave: e => e.currentTarget.style.boxShadow = 'none'
    }, rc && /*#__PURE__*/React.createElement("span", {
      style: {
        position: 'absolute',
        top: 0,
        right: 0,
        width: 40,
        height: 40,
        borderTop: '5px solid #e31837',
        borderRight: '5px solid #e31837'
      }
    }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        textTransform: 'uppercase',
        letterSpacing: '.1em',
        color: '#909dab',
        marginBottom: 8
      }
    }, it.kind), /*#__PURE__*/React.createElement("h3", {
      style: {
        margin: 0,
        padding: 0,
        fontSize: 20,
        fontWeight: 700,
        color: '#2e3c49'
      }
    }, it.name), /*#__PURE__*/React.createElement("p", {
      style: {
        marginTop: 10,
        fontSize: 13,
        color: '#445c6d',
        lineHeight: 1.55
      }
    }, it.desc)), /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 16,
        fontSize: 12,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '.08em',
        color: '#e31837'
      }
    }, "Visit Website \u203A"));
  }))));
}
window.BusinessGrid = BusinessGrid;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/mge/BusinessGrid.jsx", error: String((e && e.message) || e) }); }

// ui_kits/mge/Button.jsx
try { (() => {
const {
  useState
} = React;
function Button({
  children,
  variant = 'red',
  small,
  onClick,
  href
}) {
  const styles = {
    position: 'relative',
    display: 'inline-block',
    padding: small ? '18px 40px 16px 22px' : '22px 46px 20px 26px',
    minWidth: 200,
    border: 'none',
    fontFamily: 'var(--font-sans)',
    fontWeight: 700,
    fontSize: 14,
    textTransform: 'uppercase',
    textAlign: 'left',
    textDecoration: 'none',
    lineHeight: 1,
    cursor: 'pointer',
    letterSpacing: '.06em',
    transition: 'all 200ms'
  };
  const variants = {
    red: {
      background: '#e31837',
      color: '#fff'
    },
    dark: {
      background: '#2e3c49',
      color: '#fff'
    },
    white: {
      background: '#fff',
      color: '#2e3c49',
      border: '1px solid #e4e5e6'
    },
    outlineDark: {
      background: 'transparent',
      color: '#2e3c49',
      border: '1px solid #2e3c49'
    },
    outlineWhite: {
      background: 'transparent',
      color: '#fff',
      border: '1px solid #fff'
    }
  };
  const arrowColor = variant === 'white' || variant === 'outlineDark' ? '#e31837' : '#fff';
  return /*#__PURE__*/React.createElement("a", {
    href: href,
    onClick: onClick,
    style: {
      ...styles,
      ...variants[variant]
    }
  }, children, /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      right: small ? 18 : 22,
      top: small ? 16 : 20,
      color: arrowColor
    }
  }, "\u203A"));
}
window.Button = Button;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/mge/Button.jsx", error: String((e && e.message) || e) }); }

// ui_kits/mge/ContactBlock.jsx
try { (() => {
function ContactBlock() {
  const [submitted, setSubmitted] = React.useState(false);
  const input = {
    padding: '16px 20px',
    border: '1px solid #dadada',
    background: '#fff',
    fontFamily: 'var(--font-sans)',
    fontSize: 15,
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box'
  };
  const label = {
    display: 'block',
    fontSize: 13,
    color: '#2e3c49',
    marginBottom: 6
  };
  return /*#__PURE__*/React.createElement("section", {
    style: {
      background: '#fff',
      padding: '80px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '0 24px',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 60
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      textTransform: 'uppercase',
      letterSpacing: '.12em',
      color: '#909dab',
      marginBottom: 10
    }
  }, "Contact"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 36,
      fontWeight: 600,
      margin: 0,
      padding: 0,
      color: '#2e3c49'
    }
  }, "Talk to us", /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#e31837'
    }
  }, ".")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 15,
      color: '#445c6d',
      lineHeight: 1.6,
      marginTop: 16,
      maxWidth: 440
    }
  }, "For trade enquiries, partnership opportunities or general questions, our team is based in Sydney and responds within one business day."), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 36,
      display: 'flex',
      flexDirection: 'column',
      gap: 18
    }
  }, [{
    ic: 'phone',
    t: '1800 600 900',
    s: 'Mon–Fri, 8:30–17:00 AEST'
  }, {
    ic: 'map-marker',
    t: 'Rosebery, Sydney NSW',
    s: '2/11 Dunlop Rd, 2018'
  }, {
    ic: 'document',
    t: 'trade@mge.com.au',
    s: 'Quote requests and orders'
  }].map(r => /*#__PURE__*/React.createElement("div", {
    key: r.ic,
    style: {
      display: 'flex',
      gap: 16,
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 40,
      height: 40,
      background: '#e4e5e6',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flex: 'none'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `../../assets/icons/${r.ic}.svg`,
    style: {
      width: 18,
      height: 18
    }
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700,
      color: '#2e3c49',
      fontSize: 15
    }
  }, r.t), /*#__PURE__*/React.createElement("div", {
    style: {
      color: '#909dab',
      fontSize: 13
    }
  }, r.s)))))), /*#__PURE__*/React.createElement("div", {
    style: {
      background: '#e4e5e6',
      padding: 40
    }
  }, submitted ? /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: 340,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 56,
      height: 56,
      background: '#e31837',
      color: '#fff',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 28
    }
  }, "\u2713"), /*#__PURE__*/React.createElement("h3", {
    style: {
      marginTop: 20,
      fontSize: 22,
      color: '#2e3c49'
    }
  }, "Thanks", /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#e31837'
    }
  }, ".")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 14,
      color: '#445c6d',
      maxWidth: 320
    }
  }, "We've received your enquiry and will be in touch within one business day.")) : /*#__PURE__*/React.createElement("form", {
    onSubmit: e => {
      e.preventDefault();
      setSubmitted(true);
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: '0 0 24px',
      padding: 0,
      fontSize: 18,
      color: '#2e3c49',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '.06em'
    }
  }, "Send a message"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 14,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    style: label
  }, "Name"), /*#__PURE__*/React.createElement("input", {
    style: input,
    required: true,
    defaultValue: "",
    placeholder: "Jane Doe"
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    style: label
  }, "Company"), /*#__PURE__*/React.createElement("input", {
    style: input,
    placeholder: "Your company"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: label
  }, "Email"), /*#__PURE__*/React.createElement("input", {
    style: input,
    type: "email",
    required: true,
    placeholder: "name@company.com.au"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: label
  }, "Message"), /*#__PURE__*/React.createElement("textarea", {
    style: {
      ...input,
      height: 120,
      resize: 'vertical',
      fontFamily: 'var(--font-sans)'
    }
  })), /*#__PURE__*/React.createElement(Button, {
    variant: "red"
  }, "Send enquiry")))));
}
window.ContactBlock = ContactBlock;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/mge/ContactBlock.jsx", error: String((e && e.message) || e) }); }

// ui_kits/mge/Footer.jsx
try { (() => {
function Footer() {
  const col = (title, items) => /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: {
      color: '#fff',
      margin: '0 0 10px',
      fontSize: 13,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '.05em'
    }
  }, title), items.map(i => /*#__PURE__*/React.createElement("a", {
    key: i,
    style: {
      display: 'block',
      color: '#909dab',
      fontSize: 13,
      padding: '4px 0',
      textDecoration: 'none'
    }
  }, i)));
  const social = ['facebook', 'linkedin', 'twitter', 'youtube'];
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      background: '#2e3c49',
      color: '#909dab',
      borderBottom: '20px solid #e31837',
      fontFamily: 'var(--font-sans)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '60px 24px 40px',
      display: 'grid',
      gridTemplateColumns: '1.4fr 1fr 1fr 1fr',
      gap: 40
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      borderRight: '1px solid #445c6d',
      paddingRight: 40
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      color: '#fff',
      margin: '0 0 14px',
      fontSize: 22,
      fontWeight: 600
    }
  }, "Get in touch", /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#e31837'
    }
  }, ".")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 13,
      lineHeight: 1.6,
      margin: 0
    }
  }, "Madison Group Enterprises Pty Ltd. Sydney, NSW 2000.", /*#__PURE__*/React.createElement("br", null), "Australia-wide distribution across AV, broadcast, connectivity and mission-critical technology."), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 28
    }
  }, /*#__PURE__*/React.createElement("h4", {
    style: {
      color: '#fff',
      margin: '0 0 14px',
      fontSize: 12,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '.08em'
    }
  }, "Our Businesses"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 24,
      flexWrap: 'wrap',
      color: '#fff',
      fontSize: 13
    }
  }, ['MadisonAV', 'Madison Connectivity', 'Madison Express', 'Madison Technologies'].map(b => /*#__PURE__*/React.createElement("span", {
    key: b
  }, b))), /*#__PURE__*/React.createElement("h4", {
    style: {
      color: '#fff',
      margin: '22px 0 14px',
      fontSize: 12,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '.08em',
      paddingTop: 22,
      borderTop: '1px solid #445c6d'
    }
  }, "Our Affiliated Businesses"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 24,
      flexWrap: 'wrap',
      color: '#fff',
      fontSize: 13
    }
  }, ['Kallipr', 'CtrlOps'].map(b => /*#__PURE__*/React.createElement("span", {
    key: b
  }, b))))), col('Quick links', ['What we do', 'Who we are', 'News', 'Contact']), col('Corporate', ['Careers', 'Privacy', 'Terms', 'Modern Slavery']), /*#__PURE__*/React.createElement("div", null, col('Follow us', []), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      marginTop: 4
    }
  }, social.map(s => /*#__PURE__*/React.createElement("a", {
    key: s,
    style: {
      width: 36,
      height: 36,
      borderRadius: '50%',
      background: '#445c6d',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `../../assets/icons/${s}.svg`,
    style: {
      width: 16,
      height: 16,
      filter: 'brightness(0) invert(1)'
    }
  })))))), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '18px 24px',
      fontSize: 12,
      color: '#909dab',
      borderTop: '1px solid #445c6d',
      display: 'flex',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("span", null, "\xA9 2026 Madison Group Enterprises Pty Ltd."), /*#__PURE__*/React.createElement("span", null, "ABN 00 000 000 000")));
}
window.Footer = Footer;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/mge/Footer.jsx", error: String((e && e.message) || e) }); }

// ui_kits/mge/Header.jsx
try { (() => {
function Header({
  page,
  onNav
}) {
  const nav = ['What we do', 'Who we are', 'News', 'Careers', 'Contact'];
  const map = {
    'What we do': 'businesses',
    'Who we are': 'home',
    'News': 'home',
    'Careers': 'home',
    'Contact': 'contact'
  };
  const utilStyle = {
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: '.08em',
    color: '#2e3c49',
    cursor: 'pointer'
  };
  const businessBar = [{
    l: 'MadisonAV',
    key: 'av'
  }, {
    l: 'Madison Technologies',
    key: 'mt'
  }, {
    l: 'Madison Express',
    key: 'mex'
  }];
  return /*#__PURE__*/React.createElement("header", {
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 50,
      background: '#fff',
      boxShadow: '0 2px 4px -2px rgba(46,60,73,.4)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      borderBottom: '1px solid #e4e5e6',
      background: '#f7f7f8'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '10px 24px',
      display: 'flex',
      justifyContent: 'space-between',
      fontSize: 11,
      color: '#909dab',
      textTransform: 'uppercase',
      letterSpacing: '.08em'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#2e3c49',
      fontWeight: 700
    }
  }, "Our Businesses:"), "\xA0\xA0", businessBar.map(b => /*#__PURE__*/React.createElement("span", {
    key: b.key,
    style: {
      marginRight: 18
    }
  }, b.l))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#2e3c49',
      fontWeight: 700
    }
  }, "Affiliated:"), "\xA0\xA0", /*#__PURE__*/React.createElement("span", null, "Madison Connectivity"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 18
    }
  }, "Kallipr"), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 18
    }
  }, "CtrlOps")))), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '20px 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("a", {
    onClick: () => onNav('home'),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      textDecoration: 'none',
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/logo-mge-positive.svg",
    alt: "Madison Group Enterprises",
    style: {
      height: 42,
      display: 'block'
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 24,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/icons/search.svg",
    style: {
      width: 18,
      height: 18,
      opacity: .7,
      cursor: 'pointer'
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: utilStyle
  }, "1800 600 900"))), /*#__PURE__*/React.createElement("div", {
    style: {
      background: '#e31837'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '0 24px',
      display: 'flex',
      gap: 34,
      height: 50,
      alignItems: 'center'
    }
  }, nav.map(l => {
    const dest = map[l];
    const active = dest === page;
    return /*#__PURE__*/React.createElement("a", {
      key: l,
      onClick: () => onNav(dest),
      style: {
        color: '#fff',
        fontSize: 13,
        fontWeight: 700,
        letterSpacing: '.08em',
        textTransform: 'uppercase',
        cursor: 'pointer',
        opacity: active ? 1 : .85,
        borderBottom: active ? '2px solid #fff' : '2px solid transparent',
        padding: '14px 0'
      }
    }, l);
  }))));
}
window.Header = Header;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/mge/Header.jsx", error: String((e && e.message) || e) }); }

// ui_kits/mge/IndustryStrip.jsx
try { (() => {
function IndustryStrip({
  items
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      background: '#2e3c49',
      color: '#fff',
      padding: '48px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1320,
      margin: '0 auto',
      padding: '0 24px'
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: '0 0 28px',
      fontSize: 22,
      fontWeight: 600
    }
  }, "Industries we serve", /*#__PURE__*/React.createElement("span", {
    style: {
      color: '#e31837'
    }
  }, ".")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: `repeat(${items.length},1fr)`,
      gap: 24
    }
  }, items.map(it => /*#__PURE__*/React.createElement("div", {
    key: it.label,
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 12,
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 64,
      height: 64,
      border: '1px solid #445c6d',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#e31837',
      fontSize: 28
    }
  }, it.glyph), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '.06em'
    }
  }, it.label))))));
}
window.IndustryStrip = IndustryStrip;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/mge/IndustryStrip.jsx", error: String((e && e.message) || e) }); }

})();
