---
title: The Wolf Project - Reworking a Real-World Project
link to repo: "https://github.com/ZSturman/The-Wolf-Pack"
projects: "The Wolf Pproject"
one liner: Rebuilding The Wolf Project’s site into a structured, scalable platform to better support real rescue work.
tags: [Dogs, Firebase, Next.js, Nonprofit, Web App, Welfare]
summary: After discovering The Wolf Project through a Dodo video, I connected with the team and began rebuilding their website to better support their needs. The new version introduces structured data, dynamic content, and scalable infrastructure using Next.js, Firebase, and Cloudinary. It’s now a usable foundation that can evolve into a more complete system for showcasing cases, managing content, and supporting contributions.
series: The Wolf Project
platform: [DEV]
cover_image: imgaes/Wolf-hero.webp
updatedAt: 2026-04-18
---

A few weeks ago I watched a Dodo video about The Wolf Project that stayed with me more than I expected.

[https://www.youtube.com/watch?v=NMf8mlxO4sk](https://www.youtube.com/watch?v=NMf8mlxO4sk)

After that, I tried to find more information about what I had just watched. When I googled ‘the wolf pack’ there was obviously a lot of options so I went to their Instagram page:

[https://www.instagram.com/_wolf_project/](https://www.instagram.com/_wolf_project/)

I sent a message, Megan responded, and she made it clear that help on the site itself would actually be useful. That became the starting point.

---

## Where the Project Started

The existing site did what it needed to do at a basic level. It explained the mission, shared stories, and gave people a way to engage.

![Screenshot 2026-04-18 at 17.28.24.png](imgaes/Screenshot_2026-04-18_at_17.28.24.png)

The site had everything it needed for the moment, but it was missing the actual layers Megan was wanting like the ability to have specific animal stories showcased, specific dollar amount shown per case plus blogs and an application process for others to get on board.

---

## What I’ve Been Working On

The current version is built with Next.js and uses Firebase for authentication and data, with Cloudinary handling image storage.

![Screenshot 2026-04-18 at 17.29.59.png](imgaes/Screenshot_2026-04-18_at_17.29.59.png)

Cases, blog posts, and site-wide content are stored in Firestore, which means updates are persisted and reflected immediately on the site. This is building the first parts of the real system Megan is looking for.

That change shifts how the project can be used.

- Structured data for cases, blog posts, and shared site content

- Image uploads that don’t rely on local assets

- Seeded demo data so the site is usable without setup

There’s still work to do, especially around polish and edge cases, but the foundation is in a much better place than it was.

---

## Current State

The dev version of the site is live here:

[https://the-wolf-project-14stqkkgr-zsturmans-projects.vercel.app](https://the-wolf-project-14stqkkgr-zsturmans-projects.vercel.app/)

The original site is still available here:

[https://yourdogcanstay.com](https://yourdogcanstay.com/)

It’s still a work in progress. There are areas that need refinement, and some features that haven’t been fully implemented yet. But it’s at a point where it’s usable and where feedback is actually helpful.

If you’ve seen the story or care about the space this project is working in, there’s room to contribute, whether that’s through feedback, design suggestions, or development.

---

## What Comes Next

There are a few areas I’m focused on next:

- Tightening up editing and data validation

- Improving how donation data is handled and displayed

- Cleaning up remaining assumptions around static content

- Making sure the system is stable enough for real usage

The goal is to make sure the site can actually support the work it’s tied to, without becoming something that needs constant technical maintenance.

