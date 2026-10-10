/* JSON-LD starter blocks. Replace example values before publishing. */
(function (root) {
  "use strict";
  const publisher = { "@type": "Organization", "@id": "DOMAIN_URL#organization", name: "SITE_NAME", url: "DOMAIN_URL", logo: { "@type": "ImageObject", url: "LOGO_URL" } };
  const page = { name: "META_TITLE", url: "PAGE_URL", description: "META_DESCRIPTION", inLanguage: "PAGE_LANGUAGE", isPartOf: { "@type": "WebSite", "@id": "DOMAIN_URL#website", name: "SITE_NAME", url: "DOMAIN_URL" } };
  const article = { headline: "META_TITLE", url: "PAGE_URL", mainEntityOfPage: "PAGE_URL", description: "META_DESCRIPTION", image: "META_IMAGE", datePublished: "DATE_PUBLISHED", dateModified: "DATE_MODIFIED", inLanguage: "PAGE_LANGUAGE", author: { "@type": "Person", name: "AUTHOR_NAME" }, publisher };
  const templates = {
    Organization: { ...publisher, description: "ORGANIZATION_DESCRIPTION", sameAs: ["SOCIAL_PROFILE_URL"] },
    WebSite: { "@id": "DOMAIN_URL#website", name: "SITE_NAME", url: "DOMAIN_URL", description: "SITE_DESCRIPTION", inLanguage: "PAGE_LANGUAGE", publisher },
    CollectionPage: { "@id": "PAGE_URL#collectionpage", ...page, mainEntity: { "@type": "ItemList", itemListElement: [{ "@type": "ListItem", position: 1, name: "ITEM_NAME", url: "ITEM_URL" }] } },
    WebPage: { "@id": "PAGE_URL#webpage", ...page, primaryImageOfPage: { "@type": "ImageObject", contentUrl: "META_IMAGE" } },
    Brand: { "@id": "DOMAIN_URL#brand", name: "BRAND_NAME", url: "DOMAIN_URL", logo: "LOGO_URL", description: "BRAND_DESCRIPTION", sameAs: ["SOCIAL_PROFILE_URL"] },
    ImageObject: { "@id": "PAGE_URL#image", name: "IMAGE_NAME", contentUrl: "META_IMAGE", caption: "IMAGE_CAPTION", creditText: "IMAGE_CREDIT", license: "IMAGE_LICENSE_URL" },
    VideoObject: { "@id": "PAGE_URL#video", name: "VIDEO_NAME", description: "VIDEO_DESCRIPTION", thumbnailUrl: ["VIDEO_THUMBNAIL_URL"], uploadDate: "VIDEO_UPLOAD_DATE", contentUrl: "VIDEO_URL", duration: "VIDEO_DURATION_ISO8601" },
    BreadcrumbList: { "@id": "PAGE_URL#breadcrumb", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: "DOMAIN_URL" }, { "@type": "ListItem", position: 2, name: "META_TITLE", item: "PAGE_URL" }] },
    Article: { "@id": "PAGE_URL#article", ...article },
    BlogPosting: { "@id": "PAGE_URL#blogposting", ...article },
    Product: { "@id": "PAGE_URL#product", name: "PRODUCT_NAME", url: "PAGE_URL", description: "META_DESCRIPTION", image: "META_IMAGE", sku: "PRODUCT_SKU", brand: { "@type": "Brand", name: "BRAND_NAME" }, offers: { "@type": "Offer", url: "PAGE_URL", price: "PRODUCT_PRICE", priceCurrency: "PRICE_CURRENCY", availability: "AVAILABILITY_URL" } },
    LocalBusiness: { "@id": "DOMAIN_URL#localbusiness", name: "BUSINESS_NAME", url: "DOMAIN_URL", image: "META_IMAGE", telephone: "BUSINESS_PHONE", address: { "@type": "PostalAddress", streetAddress: "STREET_ADDRESS", addressLocality: "ADDRESS_CITY", addressRegion: "ADDRESS_REGION", postalCode: "POSTAL_CODE", addressCountry: "COUNTRY_CODE" } },
    Person: { "@id": "PAGE_URL#person", name: "PERSON_NAME", url: "PAGE_URL", jobTitle: "JOB_TITLE", image: "PERSON_IMAGE_URL", sameAs: ["SOCIAL_PROFILE_URL"] },
    FAQPage: { "@id": "PAGE_URL#faqpage", ...page, mainEntity: [{ "@type": "Question", name: "FAQ_QUESTION", acceptedAnswer: { "@type": "Answer", text: "FAQ_ANSWER" } }] },
    Service: { "@id": "PAGE_URL#service", name: "SERVICE_NAME", url: "PAGE_URL", description: "META_DESCRIPTION", serviceType: "SERVICE_TYPE", provider: publisher, areaServed: "SERVICE_AREA" }
  };
  const tokens = new Set(JSON.stringify(templates).match(/\b[A-Z]+(?:_[A-Z0-9]+)+\b/g));
  function httpUrl(value, base) {
    const url = new URL(value, base);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error("Use an HTTP or HTTPS URL without credentials.");
    return url;
  }
  function replacements(fields = {}) {
    const values = {};
    for (const token of tokens) if (typeof fields[token] === "string" && fields[token].trim()) values[token] = fields[token].trim();
    let domain;
    if (fields.DOMAIN_URL && fields.DOMAIN_URL.trim()) {
      const raw = fields.DOMAIN_URL.trim();
      domain = httpUrl(raw.includes("://") ? raw : `https://${raw}`);
      values.DOMAIN_URL = domain.origin + "/";
    }
    if (values.PAGE_URL) {
      const url = httpUrl(values.PAGE_URL, domain ? values.DOMAIN_URL : undefined);
      if (domain) { url.protocol = domain.protocol; url.host = domain.host; }
      url.hash = "";
      values.PAGE_URL = url.href;
      if (!domain) values.DOMAIN_URL = url.origin + "/";
    } else if (domain) values.PAGE_URL = values.DOMAIN_URL;
    if (values.META_IMAGE) values.META_IMAGE = httpUrl(values.META_IMAGE, values.PAGE_URL).href;
    if (values.LOGO_URL) values.LOGO_URL = httpUrl(values.LOGO_URL, values.DOMAIN_URL).href;
    return values;
  }
  function apply(value, fields) {
    const values = replacements(fields);
    function visit(item, property) {
      if (typeof item === "string") {
        if (property === "@id") {
          const match = item.match(/^(DOMAIN_URL|PAGE_URL)(#[^#]+)$/);
          if (match && values[match[1]]) return values[match[1]] + match[2];
        }
        return values[item] || item;
      }
      if (Array.isArray(item)) return item.map(child => visit(child, property));
      if (object(item)) return Object.fromEntries(Object.entries(item).map(([key, child]) => [key, key === "@context" ? child : visit(child, key)]));
      return item;
    }
    return visit(value);
  }
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  function parse(text) {
    const trimmed = text.trim();
    // Also accept one complete JSON-LD script copied from a page.
    const wrapped = trimmed.match(/^<script\b[^>]*\btype\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script\s*>$/i);
    return JSON.parse(wrapped ? wrapped[1] : trimmed);
  }
  function check(value) {
    const errors = [];
    const warnings = [];
    if (!object(value) && !Array.isArray(value)) return { errors: ["Root must be a JSON-LD object or array of objects."], warnings };
    function node(item, path, inheritedContext, top) {
      if (!object(item)) { errors.push(`${path}: expected an object.`); return; }
      const context = item["@context"] || inheritedContext;
      if (top && !context) warnings.push(`${path}: missing @context (usually https://schema.org).`);
      if (item["@graph"] !== undefined && !Array.isArray(item["@graph"])) errors.push(`${path}.@graph: expected an array.`);
      if (top && !item["@type"] && !item["@graph"] && !item["@id"]) warnings.push(`${path}: add @type or @graph to describe a schema block.`);
      if (item["@type"] !== undefined && !(typeof item["@type"] === "string" && item["@type"].trim()) && !(Array.isArray(item["@type"]) && item["@type"].length && item["@type"].every(t => typeof t === "string" && t.trim()))) errors.push(`${path}.@type: expected a nonempty string or array of strings.`);
      if (item["@id"] !== undefined && typeof item["@id"] !== "string") errors.push(`${path}.@id: expected a string.`);
      for (const [key, child] of Object.entries(item)) {
        if (key === "@context") continue;
        if (typeof child === "string" && (tokens.has(child) || (key === "@id" && /^(DOMAIN_URL|PAGE_URL)#/.test(child)))) warnings.push(`${path}.${key}: replace ${child} with actual page information or remove the optional property.`);
        if (Array.isArray(child)) child.forEach((entry, index) => { if (tokens.has(entry)) warnings.push(`${path}.${key}[${index}]: replace ${entry} before publishing.`); });
        if (Array.isArray(child)) child.forEach((entry, index) => {
          if (key === "@graph" || object(entry)) node(entry, `${path}.${key}[${index}]`, context, key === "@graph");
        });
        else if (object(child)) node(child, `${path}.${key}`, context, false);
      }
    }
    if (Array.isArray(value)) {
      if (!value.length) warnings.push("The document has no schema blocks.");
      value.forEach((item, index) => node(item, `$[${index}]`, null, true));
    } else {
      node(value, "$", null, true);
      if (Array.isArray(value["@graph"]) && !value["@graph"].length) warnings.push("The graph has no schema blocks. Add a template to start.");
    }
    return { errors, warnings };
  }
  function add(value, type, fields = {}) {
    if (!Object.prototype.hasOwnProperty.call(templates, type)) throw new Error("Unknown template.");
    if (check(value).errors.length) throw new Error("Fix the structure errors before adding a block.");
    const block = apply({ "@type": type, ...templates[type] }, fields);
    if (Array.isArray(value)) return [...value, { "@context": "https://schema.org", ...block }];
    if (Array.isArray(value["@graph"])) return { ...value, "@graph": [...value["@graph"], block] };
    // Keep any existing node and its local context intact.
    return { "@context": "https://schema.org", "@graph": [value, block] };
  }
  const api = { templates, parse, check, add, apply, replacements };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SchemaReader = api;
})(globalThis);
