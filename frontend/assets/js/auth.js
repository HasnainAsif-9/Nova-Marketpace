/* Auth pages — login & register */
(function () {
  const params = new URLSearchParams(window.location.search);

  // ---------- Login ----------
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async e => {
      e.preventDefault();
      const btn = document.getElementById("login-btn");
      btn.disabled = true;
      btn.textContent = "Signing in...";
      try {
        const res = await API.post("/auth/login", {
          email: document.getElementById("login-id").value.trim(),
          password: document.getElementById("login-pass").value,
        });
        const user = res.data.user;
        toast(`Welcome back, ${user.full_name || user.username}!`);
        const redirect = params.get("redirect");
        setTimeout(() => {
          if (redirect && redirect.startsWith("/")) window.location.href = redirect;
          else {
            const dash = user.role === "admin" ? "/admin/index.html"
              : user.role === "seller" ? "/seller/index.html" : "/buyer/index.html";
            window.location.href = dash;
          }
        }, 400);
      } catch (err) {
        toast(err.message || "Login failed", "error");
        btn.disabled = false;
        btn.textContent = "Sign In";
      }
    });
  }

  // ---------- Register ----------
  const regForm = document.getElementById("register-form");
  if (regForm) {
    let role = params.get("role") === "seller" ? "seller" : "buyer";
    const buyerBtn = document.getElementById("role-buyer");
    const sellerBtn = document.getElementById("role-seller");
    const sellerFields = document.getElementById("seller-fields");

    function setRole(r) {
      role = r;
      buyerBtn.className = `btn btn-block ${r === "buyer" ? "btn-primary" : "btn-outline"}`;
      sellerBtn.className = `btn btn-block ${r === "seller" ? "btn-primary" : "btn-outline"}`;
      sellerFields.classList.toggle("hidden", r !== "seller");
      document.getElementById("reg-store").required = r === "seller";
    }
    buyerBtn.addEventListener("click", () => setRole("buyer"));
    sellerBtn.addEventListener("click", () => setRole("seller"));
    setRole(role);

    regForm.addEventListener("submit", async e => {
      e.preventDefault();
      const pass = document.getElementById("reg-pass").value;
      const pass2 = document.getElementById("reg-pass2").value;
      if (pass !== pass2) { toast("Passwords do not match", "error"); return; }

      const btn = document.getElementById("reg-btn");
      btn.disabled = true;
      btn.textContent = "Creating account...";
      try {
        const body = {
          username: document.getElementById("reg-username").value.trim(),
          email: document.getElementById("reg-email").value.trim(),
          password: pass,
          full_name: document.getElementById("reg-fullname").value.trim(),
          phone: document.getElementById("reg-phone").value.trim(),
          role,
        };
        if (role === "seller") {
          body.store_name = document.getElementById("reg-store").value.trim();
          body.store_description = document.getElementById("reg-store-desc").value.trim();
        }
        const res = await API.post("/auth/register", body);
        const user = res.data.user;
        toast(role === "seller"
          ? "Account created! Your seller application is pending admin approval."
          : `Welcome to NovaMarket, ${user.full_name || user.username}!`);
        setTimeout(() => {
          window.location.href = role === "seller" ? "/seller/index.html" : "/buyer/index.html";
        }, 600);
      } catch (err) {
        toast(err.message || "Registration failed", "error");
        btn.disabled = false;
        btn.textContent = "Create Account";
      }
    });
  }

  // ---------- Forgot password ----------
  const forgotForm = document.getElementById("forgot-form");
  if (forgotForm) {
    forgotForm.addEventListener("submit", async e => {
      e.preventDefault();
      const btn = document.getElementById("forgot-btn");
      btn.disabled = true;
      btn.textContent = "Sending...";
      try {
        const res = await API.post("/auth/forgot-password", {
          email: document.getElementById("forgot-email").value.trim(),
        });
        toast(res.message || "If an account exists, a reset link has been sent.");
        forgotForm.innerHTML = `<p class="text-center">${Format.escapeHtml(res.message || "Check your email for the reset link.")}</p>`;
      } catch (err) {
        toast(err.message || "Request failed", "error");
        btn.disabled = false;
        btn.textContent = "Send Reset Link";
      }
    });
  }

  // ---------- Reset password ----------
  const resetForm = document.getElementById("reset-form");
  if (resetForm) {
    const token = params.get("token") || "";
    if (!token) {
      resetForm.innerHTML = `<p class="text-center text-muted">This reset link is missing its token. <a href="/forgot-password.html">Request a new one</a>.</p>`;
    } else {
      resetForm.addEventListener("submit", async e => {
        e.preventDefault();
        const pass = document.getElementById("reset-pass").value;
        const pass2 = document.getElementById("reset-pass2").value;
        if (pass !== pass2) { toast("Passwords do not match", "error"); return; }
        const btn = document.getElementById("reset-btn");
        btn.disabled = true;
        btn.textContent = "Resetting...";
        try {
          const res = await API.post("/auth/reset-password", { token, new_password: pass });
          toast(res.message || "Password reset. Please sign in.");
          setTimeout(() => { window.location.href = "/login.html"; }, 800);
        } catch (err) {
          toast(err.message || "Reset failed", "error");
          btn.disabled = false;
          btn.textContent = "Reset Password";
        }
      });
    }
  }

  // ---------- Verify email ----------
  const verifyCard = document.getElementById("verify-card");
  if (verifyCard) {
    const token = params.get("token") || "";
    const msg = document.getElementById("verify-msg");
    if (!token) {
      msg.textContent = "This verification link is missing its token.";
    } else {
      API.post("/auth/verify-email", { token })
        .then(res => {
          document.querySelector("#verify-card h1").textContent = "Email verified!";
          msg.textContent = res.message || "Your email address has been verified.";
        })
        .catch(err => {
          document.querySelector("#verify-card h1").textContent = "Verification failed";
          msg.textContent = err.message || "This link is invalid or has expired.";
        });
    }
  }
})();
