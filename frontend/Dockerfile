FROM node:20-alpine

WORKDIR /app

# Installer les dépendances
# --legacy-peer-deps : tolère les conflits vite/vitest/react
COPY package*.json ./
RUN npm install --legacy-peer-deps

# Copier le code source
COPY . .

# NEXT_PUBLIC_* doit être disponible au BUILD (baked dans le bundle JS)
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Désactiver la télémétrie Next.js
ENV NEXT_TELEMETRY_DISABLED=1

# Builder le projet SSR
RUN npm run build

# DigitalOcean injecte PORT à l'exécution (défaut 8080)
# ARG permet de surcharger via --build-arg PORT=xxxx si besoin
ARG PORT=8080
ENV PORT=$PORT
EXPOSE $PORT

ENV NODE_ENV=production

CMD ["npm", "start"]
