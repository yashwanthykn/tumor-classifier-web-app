//Checks if the user is already logged in 

window.addEventListener('DOMContentLoaded',()=>{
     const token = localStorage.getItem('token');
     if (token){
          //User already logged in, redirect to dashboard
          window.location.href='/dashboard.html';
     }
});

function showTab(tab) {
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const tabs = document.querySelectorAll('.tab-btn');
     //finds all the elements with class tab-btn
     //returns a nodeList a array-like abjects tabs[0] -login and tabs[1]-register tab
     //showtab present in the html get assigned to the tab

     if (tab === 'login') {
          loginForm.classList.add('active');
          registerForm.classList.remove('active');
          tabs[0].classList.add('active');
          tabs[1].classList.remove('active');
     }
     else {
          registerForm.classList.add('active');
          loginForm.classList.remove('active');
          tabs[1].classList.add('active');
          tabs[0].classList.remove('active');
  }
}

// Login form handler
document.getElementById('loginForm').addEventListener('submit',async(e)=>{
     e.preventDefault();
     const email=document.getElementById('login-email').value;
     //value text inside the input value
     const password=document.getElementById('login-password').value;
     const messageDiv=document.getElementById('login-message');

     messageDiv.innerHTML='<p class="loading">Logging in...</p>';


     try{
          const response=await fetch('api/auth/login',{
               method:'POST',
               headers:{
                    'Content-Type':'application/json',
               },
               body:JSON.stringify({email,password}),
          });

          const data=await response.json()

          if (!response.ok){
               throw new Error(data.detail||'Login failed');
          }

          //string token in the localstorage so the broswer i.e window can access it
          localStorage.setItem('token',data.access_token)

          messageDiv.innerHTML = '<p class="success">Login successful! Redirecting...</p>';

          setTimeout(() => {
               window.location.href = '/dashboard.html';
          },1000);
     } catch (error) {
          messageDiv.innerHTML = `<p class="error">❌ ${error.message}</p>`;
  }
});

//Register Form Handler
document.getElementById('registerForm').addEventListener('submit', async (e) => {
     e.preventDefault();
     const email = document.getElementById('register-email').value;
     const username = document.getElementById('register-username').value;
     const password = document.getElementById('register-password').value;
     const messageDiv = document.getElementById('register-message');
     
     messageDiv.innerHTML = '<p class="loading">Creating account...</p>';

     try {
          const response = await fetch('/api/auth/register', {
          method: 'POST',
          headers: {
               'Content-Type': 'application/json',
               },
          body: JSON.stringify({ email, username, password }),
          });

          const data = await response.json();

          if (!response.ok) {
               throw new Error(data.detail || 'Registration failed');
          }

          messageDiv.innerHTML = '<p class="success">✅ Account created! Please login.</p>';

          // Clear form
          document.getElementById('registerForm').reset();
    
          // Switch to login tab after 2 seconds
          setTimeout(() => {
               showTab('login');
               document.getElementById('login-email').value = email;
          }, 2000);
     
     }catch (error) {
          messageDiv.innerHTML = `<p class="error">❌ ${error.message}</p>`;
     }
});


 

