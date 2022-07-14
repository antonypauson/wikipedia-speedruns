<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
import Home from "./components/Home.vue";
</script>

<template>
  <header>
    <div class="wrapper">
      <nav>
        <RouterLink to="/">Home</RouterLink>
      </nav>
    </div>
  </header>

  <RouterView />
</template>
