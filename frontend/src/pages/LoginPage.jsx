import React from "react";

export default function LoginPage({ info }) {
  const nothingConfigured = !info.autodesk && !info.dev_login;
  return (
    <main className="login">
      <div className="login-box">
        <span className="brand" style={{ margin: 0 }}>MedIAData</span>
        <h1 className="display h1">Suivi des productions</h1>
        <p className="muted">
          Connectez-vous avec le compte Autodesk que vous utilisez pour ShotGrid. Vous verrez les productions
          auxquelles ShotGrid vous donne accès.
        </p>

        {info.login_error && (
          <div className="error-box" role="alert">{info.login_error}</div>
        )}

        {info.autodesk && (
          <a className="btn primary login-btn" href="/auth/autodesk/login">
            Se connecter avec Autodesk
          </a>
        )}
        {!info.autodesk && info.dev_login && (
          <p className="faint small">La connexion Autodesk n'est pas encore configurée (APS_CLIENT_ID).</p>
        )}
        {info.dev_login && (
          <a className="btn login-btn" href="/auth/dev-login">
            Connexion de développement (localhost)
          </a>
        )}
        {nothingConfigured && (
          <div className="error-box" role="status">
            La connexion Autodesk n'est pas encore configurée. Un administrateur doit renseigner
            <code> APS_CLIENT_ID</code> et <code>APS_CLIENT_SECRET</code> dans le fichier <code>.env</code> du serveur.
          </div>
        )}
      </div>
    </main>
  );
}
