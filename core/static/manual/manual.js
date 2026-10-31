"use strict";

const forms = [...document.querySelectorAll("form[data-method]")];
const status = document.getElementById("request-status");
const output = document.getElementById("response-body");
const cookieName = document.body.dataset.csrfCookie;
const csrfHeader = document.body.dataset.csrfHeader;
let pending = false;

function csrfToken() {
  const cookie = document.cookie.split(";").map(value => value.trim())
    .find(value => value.startsWith(`${cookieName}=`));
  return cookie ? decodeURIComponent(cookie.slice(cookieName.length + 1)) : "";
}

async function submit(form) {
  const method = form.dataset.method;
  const url = new URL(form.action, window.location.href);
  if (url.origin !== window.location.origin) {
    throw new Error("Envio para outra origem bloqueado.");
  }
  const body = {};
  for (const input of form.querySelectorAll("input[name]")) {
    if (input.name === "session_id") {
      url.pathname = url.pathname.replace("/0/", `/${encodeURIComponent(input.value)}/`);
    } else if (input.type === "checkbox") {
      body[input.name] = input.checked;
    } else if (input.value !== "") {
      body[input.name] = input.value;
    }
  }
  const headers = {Accept: "application/json"};
  const options = {method, headers, credentials: "same-origin", cache: "no-store", redirect: "error"};
  if (method === "GET") {
    for (const [name, value] of Object.entries(body)) url.searchParams.set(name, value);
  } else {
    if (!csrfToken()) {
      const bootstrap = await fetch("/api/login/", {
        credentials: "same-origin", cache: "no-store", redirect: "error",
      });
      if (!bootstrap.ok) throw new Error(`Falha ao preparar CSRF: HTTP ${bootstrap.status}.`);
    }
    const csrf = csrfToken();
    if (!csrf) throw new Error("Cookie CSRF indisponível. Confira o HTTPS e a configuração dos cookies.");
    headers[csrfHeader] = csrf;
    if (method === "POST") {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
  }
  status.textContent = `Enviando ${method} ${url.pathname}${url.search}…`;
  const response = await fetch(url, options);
  const text = await response.text();
  const retry = response.headers.get("Retry-After");
  status.textContent = `${method} ${url.pathname}${url.search} — HTTP ${response.status} ${response.statusText}`
    + (retry ? ` — tente novamente em ${retry} segundos.` : "");
  if (!text) {
    output.textContent = "Resposta sem conteúdo.";
  } else {
    try {
      output.textContent = JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      output.textContent = text;
    }
  }
}

for (const form of forms) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (pending) return;
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
    pending = true;
    output.textContent = "";
    for (const button of document.querySelectorAll("button[type=submit]")) button.disabled = true;
    try {
      await submit(form);
    } catch (error) {
      status.textContent = `Não foi possível obter a resposta: ${error.message} A operação pode ter sido concluída no servidor; confira o estado antes de repetir.`;
    } finally {
      for (const input of form.querySelectorAll('input[type="password"]')) input.value = "";
      pending = false;
      for (const button of document.querySelectorAll("button[type=submit]")) button.disabled = false;
    }
  });
  form.querySelector("fieldset").disabled = false;
}

document.getElementById("clear-result").addEventListener("click", () => {
  output.textContent = "";
  status.textContent = "Resultado limpo.";
});
