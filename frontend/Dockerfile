FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# ⚠️ Ajouter cette ligne avant le build
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ⚠️ Port
ARG PORT=8080
ENV PORT=$PORT
EXPOSE $PORT

CMD ["npm","start","--","-H","0.0.0.0"]
