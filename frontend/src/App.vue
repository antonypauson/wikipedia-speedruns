<script lang="ts">
import { RouterLink, RouterView } from "vue-router";


export default {
    el: '#nav',

    data: function () {
        return {
            username: "",
            loggedIn: false,
        }
    },

    created: function() {
          this.loggedIn = true;
          this.username = "username";
          this.isAdmin = false;
    },

    methods: {
        async handleLogout(event)
        {
            event.preventDefault();
            await fetch("/api/users/logout", {method : "POST"});
            window.location.href = "/";
        }
    }
}

</script>

<template>
  <body data-bs-spy="scroll" data-bs-target="#toc" data-bs-offset="144">
      <nav id="nav" class="navbar navbar-expand-md sticky-top bg-body">
          <div class="container-xxl py-2">

              <div class="navbar-brand d-flex align-items-end">
                  <a href="/" class="d-flex align-items-center text-center">
                      <img src="/static/assets/wslogo.svg" alt="" height="45">
                      <div class="d-flex flex-column">
                          <img src="/static/assets/wikipedia.svg" alt="" height="25">
                          <strong class="localized-slogan">Speedruns</strong>
                      </div>
                  </a>
                  <a href="/devblog" class="version-link">V. 0.1</a>
              </div>

              <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarContent">
                  <span class="navbar-toggler-icon"></span>
              </button>

              <div class="collapse navbar-collapse" id="navbarContent">

                  <div class="navbar-nav ms-auto">

                      <template v-if="loggedIn">

                          <template v-if="isAdmin">
                              <a class="nav-link" v-bind:href="'/testarticle'">Test</a>
                              <a class="nav-link" v-bind:href="'/stats'">Stats</a>
                              <a class="nav-link" v-bind:href="'/manage'">Manage</a>
                          </template>

                          <a class="nav-link" v-bind:href="'/profile/' + username">{{username}}</a>
                          <button class="btn btn-light" v-on:click="handleLogout">Logout</button>

                      </template>

                      <template v-else>

                          <a class="btn btn-light" href="/register">Register</a>
                          <a class="btn btn-light" href="/login">Login</a>

                      </template>
                  </div>
              </div>
          </div>
      </nav>

      <div class="container-xxl">
        <RouterView />
      </div>
  </body>

</template>
